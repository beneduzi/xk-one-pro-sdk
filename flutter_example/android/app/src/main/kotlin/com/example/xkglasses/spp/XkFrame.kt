package com.example.xkglasses.spp

import java.nio.ByteBuffer
import java.nio.ByteOrder

/**
 * 16-byte protocol envelope used by the XK One Pro protocol.
 */
data class XkFrame(
    val cmdOrder: Int,
    val cmd: Int,
    val rawDivideType: Int = 0,
    val offset: Long = 0L,
    val requestId: Int = 0,
    val payload: ByteArray = ByteArray(0),
    val head: Byte = CHANNEL_CONTROL
) {
    val divideType: Int get() = rawDivideType and 0x07
    val logicalLengthMod: Int get() = ((rawDivideType and 0xF8) shl 5) or ((rawDivideType shr 8) and 0xFF)
    val operation: Int get() = cmd and 0x7FFF
    val fromDevice: Boolean get() = (cmd and 0x8000) != 0
    val payloadLength: Int get() = payload.size

    fun encode(): ByteArray {
        val out = ByteArray(HEADER_SIZE + payload.size)
        val b = ByteBuffer.wrap(out).order(ByteOrder.LITTLE_ENDIAN)
        b.put(head)
        b.put((cmdOrder and 0xFF).toByte())
        b.putShort((cmd and 0xFFFF).toShort())
        b.putShort((rawDivideType and 0xFFFF).toShort())
        b.putShort((payload.size and 0xFFFF).toShort())
        b.putInt(offset.toInt())
        b.putShort(XkCrc16.compute(payload).toShort())
        b.putShort(0.toShort())
        b.put(payload)
        return out
    }

    override fun equals(other: Any?): Boolean {
        if (this === other) return true
        if (javaClass != other?.javaClass) return false
        other as XkFrame
        if (cmdOrder != other.cmdOrder) return false
        if (cmd != other.cmd) return false
        if (rawDivideType != other.rawDivideType) return false
        if (offset != other.offset) return false
        if (requestId != other.requestId) return false
        if (!payload.contentEquals(other.payload)) return false
        if (head != other.head) return false
        return true
    }

    override fun hashCode(): Int {
        var result = cmdOrder
        result = 31 * result + cmd
        result = 31 * result + rawDivideType
        result = 31 * result + offset.hashCode()
        result = 31 * result + requestId
        result = 31 * result + payload.contentHashCode()
        result = 31 * result + head.toInt()
        return result
    }

    companion object {
        const val HEADER_SIZE = 16
        const val CHANNEL_CONTROL: Byte = 0x30
        const val CHANNEL_IMAGE: Byte = 0x4A
        const val CHANNEL_CUSTOM: Byte = 0x2B

        fun createControl(
            cmdOrder: Int,
            commandNode: String,
            actionType: Int = 3,
            requestId: Int = 0,
            argument: ByteArray = ByteArray(0)
        ): XkFrame {
            val p = ByteBuffer.allocate(16 + argument.size).order(ByteOrder.LITTLE_ENDIAN)
            p.putShort((requestId and 0xFFFF).toShort())
            p.putInt(-1) // 0xFFFFFFFF
            p.putShort((actionType and 0xFFFF).toShort())
            p.put(byteArrayOf(0, 1))
            p.put(commandNode.toByteArray(Charsets.US_ASCII))
            p.putShort((argument.size and 0xFFFF).toShort())
            p.put(argument)
            return XkFrame(
                cmdOrder = cmdOrder,
                cmd = 0x0001,
                rawDivideType = 0,
                offset = 0L,
                requestId = requestId,
                payload = p.array(),
                head = CHANNEL_CONTROL
            )
        }

        fun createAck(cmdOrder: Int, targetCmdOrder: Int, channel: Byte = CHANNEL_CONTROL): XkFrame {
            return XkFrame(
                cmdOrder = cmdOrder,
                cmd = 0x0004,
                rawDivideType = 0,
                offset = 0L,
                requestId = 0,
                payload = byteArrayOf(0x01, (targetCmdOrder and 0xFF).toByte()),
                head = channel
            )
        }

        fun createImageAck(cmdOrder: Int): XkFrame {
            return XkFrame(
                cmdOrder = cmdOrder,
                cmd = 0x0009,
                rawDivideType = 0,
                offset = 0L,
                requestId = 0,
                payload = byteArrayOf(0x01),
                head = CHANNEL_IMAGE
            )
        }

        fun parse(buffer: ByteBuffer): XkFrame? {
            val start = buffer.position()
            if (buffer.remaining() < HEADER_SIZE) return null
            val h = buffer.get(start).toInt() and 255
            if (h != (CHANNEL_CONTROL.toInt() and 255) &&
                h != (CHANNEL_IMAGE.toInt() and 255) &&
                h != (CHANNEL_CUSTOM.toInt() and 255)
            ) return null

            val plen = (buffer.get(start + 6).toInt() and 255) or ((buffer.get(start + 7).toInt() and 255) shl 8)
            if (plen < 0 || buffer.remaining() < HEADER_SIZE + plen) return null

            val d = buffer.duplicate().order(ByteOrder.LITTLE_ENDIAN)
            d.position(start)
            val headByte = d.get()
            val order = d.get().toInt() and 255
            val cmd = d.short.toInt() and 65535
            val div = d.short.toInt() and 65535
            d.short // skip payload length
            val off = d.int.toLong() and 0xffffffffL
            val crc = d.short.toInt() and 65535
            d.short // skip reserved
            val p = ByteArray(plen)
            d.get(p)

            if (XkCrc16.compute(p) != crc) return null

            var req = 0
            if (p.size >= 2 && headByte == CHANNEL_CONTROL) {
                req = (p[0].toInt() and 255) or ((p[1].toInt() and 255) shl 8)
            }

            buffer.position(start + HEADER_SIZE + plen)
            return XkFrame(order, cmd, div, off, req, p, headByte)
        }
    }
}
