package com.example.xkglasses.spp

import android.bluetooth.BluetoothDevice
import android.util.Log
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

/**
 * High-level controller for connecting, querying battery, capturing and downloading photos.
 */
class XkGlassesController(private val device: BluetoothDevice, private val cacheDir: File) {

    enum class State { IDLE, CONNECTING, BOUND, PHOTO, ERROR }
    enum class Failure { BIND_REJECTED, TIMEOUT, JPEG_INVALID }

    var stateListener: ((State, Failure?) -> Unit)? = null
    var batteryListener: ((Int, Boolean) -> Unit)? = null
    var photoPushListener: ((Int) -> Unit)? = null
    var voiceButtonListener: (() -> Unit)? = null

    private val client = XkSppClient(device)
    private val photoLock = Any()
    private var bound = false
    private var photoCount = 6
    private var pkCounter = 0x8E

    init {
        client.onFrame(::handleFrame)
    }

    private fun nextOrder(step: Int = 2): Int {
        val cur = pkCounter
        pkCounter = (pkCounter + step) and 0xFF
        return cur
    }

    suspend fun connect(): Boolean = withContext(Dispatchers.IO) {
        if (bound) {
            stateListener?.invoke(State.BOUND, null)
            return@withContext true
        }
        stateListener?.invoke(State.CONNECTING, null)
        val latch = CountDownLatch(1)
        client.stateListener = { s, e ->
            if (s == XkSppClient.State.CONNECTED || s == XkSppClient.State.ERROR) latch.countDown()
        }
        client.connect()
        if (!latch.await(10, TimeUnit.SECONDS) || !client.isConnected) {
            fail(Failure.TIMEOUT)
            return@withContext false
        }
        try {
            val binds = XkSessionTemplates.bindSequence()
            binds.forEach {
                client.send(it)
                Thread.sleep(200)
            }
            Thread.sleep(1500)
            val setup = XkSessionTemplates.setupSequence()
            setup.forEach {
                client.send(it)
                Thread.sleep(150)
            }
            Thread.sleep(300)
            stateListener?.invoke(State.BOUND, null)
            bound = true
            queryBattery()
            true
        } catch (t: Throwable) {
            Log.e(TAG, "Bind/setup failed: ${t.message}", t)
            fail(Failure.BIND_REJECTED)
            false
        }
    }

    suspend fun capturePhoto(timeoutMs: Long = 20000): File? = withContext(Dispatchers.IO) {
        if (!connect()) return@withContext null
        stateListener?.invoke(State.PHOTO, null)

        val readyLatch = CountDownLatch(1)
        val listener = client.onFrame { f ->
            val p = f.payload
            if (p.size >= 14 && f.head == XkFrame.CHANNEL_CONTROL) {
                val tag = String(p, 10, 4, Charsets.US_ASCII)
                if (tag == "57B1" && f.fromDevice) {
                    client.send(XkFrame.createAck(f.cmdOrder, f.cmdOrder))
                } else if (tag == "7320" && f.fromDevice) {
                    val count = if (p.size >= 18) {
                        ((p[16].toInt() and 0xFF) shl 8) or (p[17].toInt() and 0xFF)
                    } else {
                        p.last().toInt() and 0xFF
                    }
                    if (count in 1..20) photoCount = count
                    client.send(XkFrame.createAck(f.cmdOrder, f.cmdOrder))
                    readyLatch.countDown()
                }
            }
        }

        try {
            synchronized(photoLock) {
                client.send(XkSessionTemplates.photo("57B0", cmdOrder = 0x24))
            }
            readyLatch.await(timeoutMs, TimeUnit.MILLISECONDS)
        } finally {
            client.removeFrameListener(listener)
        }

        downloadPhotos(timeoutMs)
    }

    suspend fun downloadPhotos(timeoutMs: Long = 15000): File? = withContext(Dispatchers.IO) {
        synchronized(photoLock) { downloadPhotosSerialized(timeoutMs) }
    }

    private fun downloadPhotosSerialized(timeoutMs: Long): File? {
        if (!bound) return null
        stateListener?.invoke(State.PHOTO, null)

        val count = if (photoCount > 0) photoCount else 6
        val reassembler = XkImageReassembler()
        reassembler.setElementCount(count)

        var txOrder = 0x28
        var lastReplyOrder = -1

        try {
            for (i in 1..count) {
                reassembler.startElement(i)

                val replyLatch = CountDownLatch(1)
                val elementDoneLatch = CountDownLatch(1)
                val currentTxOrder = txOrder
                val frameListener = client.onFrame { f ->
                    if (f.head == XkFrame.CHANNEL_CONTROL && f.payload.size >= 14) {
                        val tag = String(f.payload, 10, 4, Charsets.US_ASCII)
                        if (tag == "7300" && f.fromDevice && f.cmdOrder > lastReplyOrder) {
                            lastReplyOrder = f.cmdOrder
                            client.send(XkFrame.createAck(cmdOrder = currentTxOrder + 1, targetCmdOrder = f.cmdOrder))
                            replyLatch.countDown()
                        }
                    } else if (f.head == XkFrame.CHANNEL_IMAGE) {
                        try {
                            val needsAck = reassembler.feedImageFrame(f)
                            if (needsAck) {
                                client.send(XkSessionTemplates.photo("4A0009", cmdOrder = currentTxOrder + 2))
                            }
                            if (f.divideType == 0 || f.divideType == 3) {
                                elementDoneLatch.countDown()
                            }
                        } catch (t: Throwable) {
                            Log.e(TAG, "Image fragment error: ${t.message}", t)
                        }
                    }
                }

                try {
                    val reqId = 0x003D + 4 * (i - 1)
                    val req = XkSessionTemplates.photo("7300", index = i, cmdOrder = txOrder, requestId = reqId)
                    client.send(req)

                    if (!replyLatch.await(timeoutMs, TimeUnit.MILLISECONDS)) return null
                    if (!elementDoneLatch.await(timeoutMs, TimeUnit.MILLISECONDS)) return null

                    txOrder += 2
                } finally {
                    client.removeFrameListener(frameListener)
                }
            }

            // Finish transfer
            client.send(XkSessionTemplates.photo("7500", cmdOrder = txOrder))

            // Build JPEG
            val jpegBytes = reassembler.buildJpeg()
            stateListener?.invoke(State.BOUND, null)
            return saveJpeg(jpegBytes)
        } catch (t: Throwable) {
            Log.e(TAG, "Download JPEG failure: ${t.message}", t)
            fail(Failure.JPEG_INVALID)
            return null
        }
    }

    private fun handleFrame(f: XkFrame) {
        val p = f.payload
        val tag = if (p.size >= 14) String(p, 10, 4, Charsets.US_ASCII) else ""

        if (tag in setOf("C101", "C107") && f.fromDevice) {
            client.send(XkFrame.createAck(cmdOrder = nextOrder(), targetCmdOrder = f.cmdOrder))
            if (tag == "C101") voiceButtonListener?.invoke()
            return
        }

        if (tag == "1001" && f.fromDevice) {
            try {
                val jsonStart = p.indexOf('{'.code.toByte())
                val jsonEnd = p.lastIndexOf('}'.code.toByte())
                if (jsonStart >= 0 && jsonEnd > jsonStart) {
                    val jsonStr = String(p.copyOfRange(jsonStart, jsonEnd + 1), Charsets.UTF_8)
                    val json = org.json.JSONObject(jsonStr)
                    val battStr = json.optString("battery_main", "")
                    val battInt = battStr.toIntOrNull()
                    if (battInt != null && battInt in 0..100) {
                        batteryListener?.invoke(battInt, false)
                    }
                }
            } catch (t: Throwable) {
                Log.w(TAG, "Error parsing battery info: ${t.message}")
            }
            return
        }

        if (tag == "57A0" && f.fromDevice && p.size >= 18) {
            val b16 = p[16].toInt() and 0xFF
            val b17 = p[17].toInt() and 0xFF
            var level: Int? = null
            var charging = false
            if (b17 in 0..100 && b16 in 0..1) {
                charging = (b16 == 1)
                level = b17
            } else if (b16 in 0..100 && b17 in 0..1) {
                charging = (b17 == 1)
                level = b16
            }
            if (level != null && level > 0) {
                batteryListener?.invoke(level, charging)
            }
        }
    }

    fun queryBattery() = runCatching {
        synchronized(photoLock) {
            val req = XkFrame.createControl(
                cmdOrder = nextOrder(),
                commandNode = "1001",
                actionType = 1,
                requestId = nextOrder(1),
                argument = byteArrayOf(0)
            )
            client.send(req)
        }
    }

    fun sendKeepAlive() = runCatching {
        synchronized(photoLock) {
            client.send(XkSessionTemplates.keepAlive(nextOrder()))
        }
    }

    private fun saveJpeg(b: ByteArray): File {
        val f = File(cacheDir, "xk_photo_${System.currentTimeMillis()}.jpg")
        f.writeBytes(b)
        return f
    }

    private fun fail(f: Failure) {
        stateListener?.invoke(State.ERROR, f)
    }

    fun disconnect() {
        bound = false
        client.disconnect()
        stateListener?.invoke(State.IDLE, null)
    }

    companion object {
        private const val TAG = "XkGlassesController"
    }
}
