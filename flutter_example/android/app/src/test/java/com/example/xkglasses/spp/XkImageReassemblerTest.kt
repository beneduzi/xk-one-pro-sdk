package com.example.xkglasses.spp

import java.nio.ByteBuffer
import java.nio.ByteOrder
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class XkImageReassemblerTest {

    @Test
    fun reassembleFragmentedAndUnfragmentedElements() {
        val reassembler = XkImageReassembler()
        reassembler.setElementCount(2)

        // Element 1: fragmented into 2 packets (divideType 1 and 3)
        reassembler.startElement(1)

        // Element 1 content: 5 bytes metadata + JPEG header (FF D8 00 11 22) = 10 bytes
        val meta1 = byteArrayOf(0x0A, 0x00, 0x00, 0x00, 0x00) // length 10 LE, mediaType 0
        val jpegPart1 = byteArrayOf(0xFF.toByte(), 0xD8.toByte(), 0x00, 0x11, 0x22)
        val element1Full = meta1 + jpegPart1

        // Packet 1: divideType = 1, cmdIdx = 0, first 6 bytes of element1Full
        val p1Payload = ByteBuffer.allocate(4 + 6).order(ByteOrder.LITTLE_ENDIAN)
            .putInt(0) // cmdIdx = 0
            .put(element1Full.copyOfRange(0, 6))
            .array()
        val frame1 = XkFrame(
            cmdOrder = 10,
            cmd = 0x8001,
            rawDivideType = 1, // divideType = 1
            payload = p1Payload,
            head = XkFrame.CHANNEL_IMAGE
        )
        assertFalse(reassembler.feedImageFrame(frame1))

        // Packet 2: divideType = 3, cmdIdx = 1, remaining 4 bytes of element1Full
        val p2Payload = ByteBuffer.allocate(4 + 4).order(ByteOrder.LITTLE_ENDIAN)
            .putInt(1) // cmdIdx = 1
            .put(element1Full.copyOfRange(6, 10))
            .array()
        val frame2 = XkFrame(
            cmdOrder = 10,
            cmd = 0x8001,
            rawDivideType = 3 or (10 shl 8), // divideType = 3, logical length mod = 10
            payload = p2Payload,
            head = XkFrame.CHANNEL_IMAGE
        )
        assertTrue(reassembler.feedImageFrame(frame2)) // divideType 3 requires 4A0009 ACK

        // Element 2: unfragmented (divideType = 0)
        reassembler.startElement(2)

        val meta2 = byteArrayOf(0x09, 0x00, 0x00, 0x00, 0x00)
        val jpegPart2 = byteArrayOf(0x33, 0x44, 0xFF.toByte(), 0xD9.toByte())
        val element2Full = meta2 + jpegPart2

        val frame3 = XkFrame(
            cmdOrder = 12,
            cmd = 0x8001,
            rawDivideType = 0 or (9 shl 8), // divideType = 0
            payload = element2Full, // no cmdIdx in unfragmented payload
            head = XkFrame.CHANNEL_IMAGE
        )
        assertFalse(reassembler.feedImageFrame(frame3)) // divideType 0 does NOT receive 4A0009

        assertTrue(reassembler.isComplete)

        val assembledJpeg = reassembler.buildJpeg()
        assertArrayEquals(jpegPart1 + jpegPart2, assembledJpeg)
        assertEquals(0xFF.toByte(), assembledJpeg[0])
        assertEquals(0xD8.toByte(), assembledJpeg[1])
        assertEquals(0xFF.toByte(), assembledJpeg[assembledJpeg.size - 2])
        assertEquals(0xD9.toByte(), assembledJpeg[assembledJpeg.size - 1])
    }

    @Test(expected = IllegalStateException::class)
    fun corruptedCmdIdxThrows() {
        val reassembler = XkImageReassembler()
        reassembler.setElementCount(1)
        reassembler.startElement(1)

        val payload = ByteBuffer.allocate(4 + 5).order(ByteOrder.LITTLE_ENDIAN)
            .putInt(5) // incorrect cmdIdx (expected 0)
            .put(byteArrayOf(1, 2, 3, 4, 5))
            .array()

        val frame = XkFrame(
            cmdOrder = 10,
            cmd = 0x8001,
            rawDivideType = 1,
            payload = payload,
            head = XkFrame.CHANNEL_IMAGE
        )
        reassembler.feedImageFrame(frame)
    }

    @Test(expected = IllegalStateException::class)
    fun incompleteImageThrowsOnBuild() {
        val reassembler = XkImageReassembler()
        reassembler.setElementCount(3)
        reassembler.buildJpeg()
    }
}
