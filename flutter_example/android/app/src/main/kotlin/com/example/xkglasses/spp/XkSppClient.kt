package com.example.xkglasses.spp

import android.annotation.SuppressLint
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothSocket
import android.util.Log
import java.io.InputStream
import java.io.OutputStream
import java.nio.ByteBuffer
import java.util.UUID
import java.util.concurrent.CopyOnWriteArrayList

/**
 * Low-level RFCOMM SPP client on Channel 8.
 */
class XkSppClient(private val device: BluetoothDevice) {

    enum class State { DISCONNECTED, CONNECTING, CONNECTED, ERROR }

    var stateListener: ((State, Throwable?) -> Unit)? = null
    val isConnected: Boolean get() = socket?.isConnected == true && state == State.CONNECTED

    private var state: State = State.DISCONNECTED
        set(value) {
            field = value
            stateListener?.invoke(value, lastError)
        }

    private var socket: BluetoothSocket? = null
    private var outStream: OutputStream? = null
    private var inStream: InputStream? = null
    private var readerThread: Thread? = null
    private var lastError: Throwable? = null

    private val frameListeners = CopyOnWriteArrayList<(XkFrame) -> Unit>()
    private val buffer = ByteBuffer.allocate(1024 * 1024)

    fun onFrame(listener: (XkFrame) -> Unit): (XkFrame) -> Unit {
        frameListeners.add(listener)
        return listener
    }

    fun removeFrameListener(listener: (XkFrame) -> Unit) {
        frameListeners.remove(listener)
    }

    @SuppressLint("MissingPermission")
    fun connect() {
        if (state == State.CONNECTED || state == State.CONNECTING) return
        state = State.CONNECTING
        lastError = null

        Thread {
            try {
                var s: BluetoothSocket? = null
                runCatching {
                    val method = device.javaClass.getMethod("createRfcommSocket", Int::class.javaPrimitiveType)
                    s = method.invoke(device, 8) as BluetoothSocket
                }
                if (s == null) {
                    s = device.createRfcommSocketToServiceRecord(SPP_UUID)
                }
                socket = s
                s!!.connect()

                inStream = s!!.inputStream
                outStream = s!!.outputStream
                state = State.CONNECTED
                startReader()
            } catch (t: Throwable) {
                Log.e(TAG, "Socket connection failed: ${t.message}", t)
                lastError = t
                disconnect()
                state = State.ERROR
            }
        }.start()
    }

    private fun startReader() {
        readerThread = Thread {
            val readBuf = ByteArray(8192)
            try {
                while (state == State.CONNECTED) {
                    val stream = inStream ?: break
                    val bytesRead = stream.read(readBuf)
                    if (bytesRead <= 0) break

                    synchronized(buffer) {
                        if (buffer.remaining() < bytesRead) {
                            buffer.compact()
                        }
                        buffer.put(readBuf, 0, bytesRead)
                        buffer.flip()

                        while (true) {
                            val frame = XkFrame.parse(buffer) ?: break
                            for (l in frameListeners) {
                                runCatching { l(frame) }
                            }
                        }
                        buffer.compact()
                    }
                }
            } catch (t: Throwable) {
                if (state == State.CONNECTED) {
                    Log.e(TAG, "Reader thread loop error: ${t.message}")
                    lastError = t
                    state = State.ERROR
                }
            } finally {
                disconnect()
            }
        }.apply {
            name = "XkSppReader"
            start()
        }
    }

    fun send(frame: XkFrame): Boolean {
        return runCatching {
            val bytes = frame.encode()
            outStream?.write(bytes)
            outStream?.flush()
            true
        }.getOrElse {
            Log.e(TAG, "Send failed: ${it.message}")
            false
        }
    }

    fun disconnect() {
        if (state == State.DISCONNECTED) return
        state = State.DISCONNECTED
        runCatching { inStream?.close() }
        runCatching { outStream?.close() }
        runCatching { socket?.close() }
        inStream = null
        outStream = null
        socket = null
        readerThread = null
    }

    companion object {
        private const val TAG = "XkSppClient"
        val SPP_UUID: UUID = UUID.fromString("00001101-0000-1000-8000-00805F9B34FB")
    }
}
