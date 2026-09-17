package com.example.xkglasses.spp

import java.nio.ByteBuffer
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class XkFrameTest {

    @Test
    fun roundTrip() {
        val f = XkFrame(
            cmdOrder = 3,
            cmd = 0x0100,
            rawDivideType = 0x13,
            offset = 7L,
            requestId = 9,
            payload = byteArrayOf(1, 2, 3),
            head = XkFrame.CHANNEL_CONTROL
        )
        val p = XkFrame.parse(ByteBuffer.wrap(f.encode()))!!
        assertEquals(f.cmdOrder, p.cmdOrder)
        assertEquals(f.cmd, p.cmd)
        assertEquals(f.divideType, p.divideType)
        assertEquals(f.head, p.head)
        assertArrayEquals(f.payload, p.payload)
    }

    @Test
    fun realLogFrameValidation() {
        // Frame captured from a real XK One Pro session
        val hex = "4a2a018013692a0000000000c1ff000001000000d5d6d7d8d9dae2e3e4e5e6e7e8e9eaf2f3f4f5f6f7f8f9faffda000c03010002110311003f00"
        val raw = hex.chunked(2).map { it.toInt(16).toByte() }.toByteArray()
        val frame = XkFrame.parse(ByteBuffer.wrap(raw))

        assertNotNull(frame)
        assertEquals(XkFrame.CHANNEL_IMAGE, frame!!.head)
        assertEquals(42, frame.cmdOrder)
        assertEquals(0x8001, frame.cmd)
        assertTrue(frame.fromDevice)
        assertEquals(1, frame.operation)
        assertEquals(3, frame.divideType)
        assertEquals(617, frame.logicalLengthMod)
        assertEquals(42, frame.payloadLength)
    }

    @Test
    fun tamper() {
        val b = XkFrame(0, 1, 0, 0, 0, byteArrayOf(4)).encode()
        b[16] = 5 // modify payload -> CRC must fail
        assertNull(XkFrame.parse(ByteBuffer.wrap(b)))
    }

    @Test
    fun split() {
        val b = XkFrame(1, 2, 0, 0, 0, byteArrayOf(1, 2, 3, 4)).encode()
        var x = ByteArray(0)
        for (c in b) {
            x += c
            if (x.size < b.size) {
                assertNull(XkFrame.parse(ByteBuffer.wrap(x)))
            } else {
                assertNotNull(XkFrame.parse(ByteBuffer.wrap(x)))
            }
        }
    }

    /**
     * Locks in the control-payload framing validated on real hardware:
     * [pk_id:2 LE][FFFFFFFF][action:2 LE][0001][node:4][len:2 BE][format:1=0x00][data].
     * A wrong length (off-by-one) or little-endian order makes the device reply with a
     * generic 18-byte response and then drop the link.
     */
    @Test
    fun controlLengthIsBigEndianAndExcludesFormatByte() {
        val f = XkFrame.createControl(
            cmdOrder = 0, commandNode = "0001", actionType = 3, requestId = 1,
            argument = ByteArray(61) { 'Z'.code.toByte() }
        )
        val p = f.payload
        assertEquals(78, p.size)                       // 16 + 1 format + 61 data
        assertEquals(0x00, p[14].toInt() and 0xFF)     // 61, big-endian
        assertEquals(0x3D, p[15].toInt() and 0xFF)
        assertEquals(0x00, p[16].toInt() and 0xFF)     // format byte
        assertEquals('Z'.code.toByte(), p[17])
    }

    @Test
    fun controlWithoutDataHasZeroLengthAndFormatByte() {
        val f = XkFrame.createControl(cmdOrder = 0, commandNode = "7100", actionType = 1)
        assertEquals(17, f.payload.size)
        assertEquals(0x00, f.payload[14].toInt() and 0xFF)
        assertEquals(0x00, f.payload[15].toInt() and 0xFF)
        assertEquals(0x00, f.payload[16].toInt() and 0xFF)
    }
}
