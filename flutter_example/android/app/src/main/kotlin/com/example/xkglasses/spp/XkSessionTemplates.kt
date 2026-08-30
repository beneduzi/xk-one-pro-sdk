package com.example.xkglasses.spp

import java.nio.ByteBuffer
import java.nio.ByteOrder

/**
 * Encodes bind frames, setup sequences, capture and photo request templates.
 */
object XkSessionTemplates {

    fun bindSequence(): List<XkFrame> {
        val chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
        val token = (1..61).map { chars.random() }.joinToString("")
        val tokenBytes = byteArrayOf(0) + token.toByteArray(Charsets.US_ASCII)
        val blobBytes = byteArrayOf(0) + ByteArray(40) { (it * 7).toByte() }

        val f1 = XkFrame.createControl(cmdOrder = 0, commandNode = "0001", actionType = 3, requestId = 1, argument = tokenBytes)
        val f2 = XkFrame.createControl(cmdOrder = 0, commandNode = "0002", actionType = 3, requestId = 4, argument = blobBytes)
        return listOf(f1, f2)
    }

    fun setupSequence(): List<XkFrame> {
        val frames = mutableListOf<XkFrame>()
        var order = 0x6C

        fun add(node: String, action: Int = 1, req: Int = 0x95, arg: ByteArray = ByteArray(0)) {
            frames.add(XkFrame.createControl(cmdOrder = order++, commandNode = node, actionType = action, requestId = req, argument = arg))
            frames.add(XkFrame.createAck(cmdOrder = order++, targetCmdOrder = order - 1))
        }

        add("7100", 1, 0x95)
        add("102E", 3, 0x98, "1f1823e0e2896cdb8012a3ac083a35e6".toByteArray(Charsets.US_ASCII))
        add("7110", 1, 0x9A)
        add("1001", 1, 0xA3)
        add("1003", 1, 0xA6)
        add("2410", 1, 0xA9)
        add("2420", 2, 0xAE, "en".toByteArray(Charsets.US_ASCII))
        add("C10A", 3, 0xAC)
        add("C104", 2, 0xB0)
        add("57A0", 3, 0xB3, byteArrayOf(0))
        add("5770", 3, 0xB5, byteArrayOf(0))
        add("5713", 1, 0xBE)
        add("57B0", 3, 0xC4)

        return frames
    }

    fun photo(
        node: String,
        index: Int? = null,
        cmdOrder: Int = 0x24,
        requestId: Int = 0xC4
    ): XkFrame {
        return when (node) {
            "57B0" -> XkFrame.createControl(cmdOrder = cmdOrder, commandNode = "57B0", actionType = 3, requestId = requestId)
            "7320" -> XkFrame.createControl(cmdOrder = cmdOrder, commandNode = "7320", actionType = 3, requestId = 0x20)
            "7300" -> {
                val idx = (index ?: 1).toByte()
                XkFrame.createControl(cmdOrder = cmdOrder, commandNode = "7300", actionType = 2, requestId = requestId, argument = byteArrayOf(0, idx))
            }
            "4A0009" -> XkFrame.createImageAck(cmdOrder = cmdOrder)
            "7500" -> XkFrame.createControl(cmdOrder = cmdOrder, commandNode = "7500", actionType = 3, requestId = 0x56)
            else -> throw IllegalArgumentException("Unknown photo node: $node")
        }
    }

    fun keepAlive(cmdOrder: Int = 0x80): XkFrame {
        return XkFrame(
            cmdOrder = cmdOrder,
            cmd = 0x0004,
            rawDivideType = 0,
            offset = 0L,
            requestId = 0,
            payload = byteArrayOf(0x01, 0x06),
            head = XkFrame.CHANNEL_CONTROL
        )
    }
}
