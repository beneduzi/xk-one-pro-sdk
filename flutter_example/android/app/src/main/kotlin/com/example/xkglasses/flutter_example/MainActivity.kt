package com.example.xkglasses.flutter_example

import android.annotation.SuppressLint
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothManager
import android.content.ContentValues
import android.content.Context
import android.media.MediaScannerConnection
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import android.util.Log
import com.example.xkglasses.spp.XkGlassesController
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.EventChannel
import io.flutter.plugin.common.MethodChannel
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File
import java.io.FileInputStream
import java.io.FileOutputStream

class MainActivity : FlutterActivity() {

    private val scope = CoroutineScope(Dispatchers.Main)
    private var controller: XkGlassesController? = null
    private var eventSink: EventChannel.EventSink? = null

    private var currentBattery = -1
    private var isCharging = false

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)

        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, METHOD_CHANNEL).setMethodCallHandler { call, result ->
            when (call.method) {
                "getBondedDevices" -> {
                    result.success(getBondedDevices())
                }
                "connect" -> {
                    val mac = call.argument<String>("mac")
                    if (mac.isNullOrBlank()) {
                        result.error("INVALID_MAC", "MAC address is required", null)
                        return@setMethodCallHandler
                    }
                    connectToDevice(mac, result)
                }
                "disconnect" -> {
                    controller?.disconnect()
                    controller = null
                    result.success(true)
                }
                "takePhoto" -> {
                    takePhoto(result)
                }
                "saveToGallery" -> {
                    val path = call.argument<String>("path")
                    if (path != null) {
                        val saved = saveImageToGallery(File(path))
                        result.success(saved)
                    } else {
                        result.error("INVALID_PATH", "Path is required", null)
                    }
                }
                "getBattery" -> {
                    result.success(mapOf("level" to currentBattery, "charging" to isCharging))
                }
                else -> result.notImplemented()
            }
        }

        EventChannel(flutterEngine.dartExecutor.binaryMessenger, EVENT_CHANNEL).setStreamHandler(
            object : EventChannel.StreamHandler {
                override fun onListen(arguments: Any?, events: EventChannel.EventSink?) {
                    eventSink = events
                }

                override fun onCancel(arguments: Any?) {
                    eventSink = null
                }
            }
        )
    }

    @SuppressLint("MissingPermission")
    private fun getBondedDevices(): List<Map<String, String>> {
        val bluetoothManager = getSystemService(Context.BLUETOOTH_SERVICE) as? BluetoothManager
        val adapter = bluetoothManager?.adapter ?: BluetoothAdapter.getDefaultAdapter() ?: return emptyList()
        return adapter.bondedDevices.map { device ->
            mapOf(
                "name" to (device.name ?: "Desconhecido"),
                "address" to device.address
            )
        }
    }

    @SuppressLint("MissingPermission")
    private fun connectToDevice(mac: String, result: MethodChannel.Result) {
        val bluetoothManager = getSystemService(Context.BLUETOOTH_SERVICE) as? BluetoothManager
        val adapter = bluetoothManager?.adapter ?: BluetoothAdapter.getDefaultAdapter()
        val device = runCatching { adapter?.getRemoteDevice(mac) }.getOrNull()
        if (device == null) {
            result.error("DEVICE_NOT_FOUND", "Bluetooth device not found with MAC $mac", null)
            return
        }

        controller?.disconnect()
        val ctrl = XkGlassesController(device, cacheDir)
        controller = ctrl

        ctrl.stateListener = { state, failure ->
            scope.launch {
                eventSink?.success(mapOf(
                    "type" to "state",
                    "state" to state.name,
                    "failure" to failure?.name
                ))
            }
        }

        ctrl.batteryListener = { level, charging ->
            currentBattery = level
            isCharging = charging
            scope.launch {
                eventSink?.success(mapOf(
                    "type" to "battery",
                    "level" to level,
                    "charging" to charging
                ))
            }
        }

        ctrl.voiceButtonListener = {
            scope.launch {
                eventSink?.success(mapOf("type" to "button_pressed"))
                // Auto capture photo when physical button is pressed!
                val photoFile = ctrl.capturePhoto()
                if (photoFile != null) {
                    val galleryUri = saveImageToGallery(photoFile)
                    eventSink?.success(mapOf(
                        "type" to "photo_captured",
                        "path" to photoFile.absolutePath,
                        "galleryUri" to galleryUri
                    ))
                }
            }
        }

        scope.launch {
            val ok = ctrl.connect()
            result.success(ok)
        }
    }

    private fun takePhoto(result: MethodChannel.Result) {
        val ctrl = controller
        if (ctrl == null) {
            result.error("NOT_CONNECTED", "Glasses not connected", null)
            return
        }
        scope.launch {
            val file = ctrl.capturePhoto()
            if (file != null) {
                val galleryUri = saveImageToGallery(file)
                result.success(mapOf(
                    "path" to file.absolutePath,
                    "galleryUri" to galleryUri
                ))
            } else {
                result.error("CAPTURE_FAILED", "Failed to capture or download photo", null)
            }
        }
    }

    /**
     * Saves a captured image file into the Android MediaStore / Pictures Gallery.
     */
    private fun saveImageToGallery(sourceFile: File): String? {
        if (!sourceFile.exists()) return null
        return try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                val values = ContentValues().apply {
                    put(MediaStore.Images.Media.DISPLAY_NAME, "XK_${System.currentTimeMillis()}.jpg")
                    put(MediaStore.Images.Media.MIME_TYPE, "image/jpeg")
                    put(MediaStore.Images.Media.RELATIVE_PATH, Environment.DIRECTORY_PICTURES + "/XKGlasses")
                    put(MediaStore.Images.Media.IS_PENDING, 1)
                }
                val uri = contentResolver.insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, values)
                if (uri != null) {
                    contentResolver.openOutputStream(uri)?.use { out ->
                        FileInputStream(sourceFile).use { input ->
                            input.copyTo(out)
                        }
                    }
                    values.clear()
                    values.put(MediaStore.Images.Media.IS_PENDING, 0)
                    contentResolver.update(uri, values, null, null)
                    uri.toString()
                } else null
            } else {
                val picturesDir = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_PICTURES)
                val targetDir = File(picturesDir, "XKGlasses").apply { mkdirs() }
                val targetFile = File(targetDir, "XK_${System.currentTimeMillis()}.jpg")
                FileInputStream(sourceFile).use { input ->
                    FileOutputStream(targetFile).use { output ->
                        input.copyTo(output)
                    }
                }
                MediaScannerConnection.scanFile(this, arrayOf(targetFile.absolutePath), arrayOf("image/jpeg"), null)
                targetFile.absolutePath
            }
        } catch (t: Throwable) {
            Log.e("MainActivity", "Failed to save image to gallery: ${t.message}", t)
            null
        }
    }

    override fun onDestroy() {
        controller?.disconnect()
        super.onDestroy()
    }

    companion object {
        const val METHOD_CHANNEL = "com.example.xkglasses/methods"
        const val EVENT_CHANNEL = "com.example.xkglasses/events"
    }
}
