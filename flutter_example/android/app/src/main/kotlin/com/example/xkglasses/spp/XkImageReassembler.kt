package com.example.xkglasses.spp

import java.io.ByteArrayOutputStream

/**
 * Reassembles a JPEG image from XK One Pro protocol frames.
 */
class XkImageReassembler {

    companion object {
        const val ELEMENT_METADATA_SIZE = 5
        const val PACKED_LENGTH_MASK = 0x1FFF
        val JPEG_START = byteArrayOf(0xFF.toByte(), 0xD8.toByte())
        val JPEG_END = byteArrayOf(0xFF.toByte(), 0xD9.toByte())
    }

    var expectedElementCount: Int? = null
        private set

    private val completedElements = mutableMapOf<Int, ByteArray>()
    private var activeElementIndex: Int? = null
    private var activeCommandOrder: Int? = null
    private var activeLogicalLengthMod: Int? = null
    private var activeNextCmdIdx: Long = 0L
    private val activeFragments = mutableListOf<ByteArray>()

    val isComplete: Boolean
        get() {
            val count = expectedElementCount ?: return false
            if (count <= 0) return false
            for (i in 1..count) {
                if (!completedElements.containsKey(i)) return false
            }
            return true
        }

    fun setElementCount(count: Int) {
        require(count > 0) { "Element count must be > 0, got $count" }
        expectedElementCount = count
    }

    fun startElement(index: Int) {
        val count = expectedElementCount
        if (count != null && (index < 1 || index > count)) {
            throw IllegalArgumentException("Element index $index outside expected 1..$count")
        }
        activeElementIndex = index
        activeCommandOrder = null
        activeLogicalLengthMod = null
        activeNextCmdIdx = 0L
        activeFragments.clear()
    }

    fun feedImageFrame(frame: XkFrame): Boolean {
        require(frame.head == XkFrame.CHANNEL_IMAGE) {
            "Expected channel 0x4A, got 0x${(frame.head.toInt() and 0xFF).toString(16)}"
        }

        val divideType = frame.divideType
        val index = activeElementIndex ?: throw IllegalStateException("No active element requested for image frame")

        when (divideType) {
            0 -> {
                val rawElement = frame.payload.copyOf()
                storeElement(index, rawElement)
                activeElementIndex = null
                return false
            }
            1 -> {
                activeCommandOrder = frame.cmdOrder
                activeLogicalLengthMod = frame.logicalLengthMod
                activeNextCmdIdx = 0L
                activeFragments.clear()
                appendFragment(frame)
                return false
            }
            2 -> {
                appendFragment(frame)
                return false
            }
            3 -> {
                appendFragment(frame)
                val rawElement = activeFragments.fold(ByteArrayOutputStream()) { acc, part ->
                    acc.write(part)
                    acc
                }.toByteArray()

                storeElement(index, rawElement)
                activeElementIndex = null
                activeFragments.clear()
                return true
            }
            else -> throw IllegalArgumentException("Unknown divideType: $divideType")
        }
    }

    private fun appendFragment(frame: XkFrame) {
        if (frame.payload.size < 4) {
            throw IllegalArgumentException("Fragmented 4A frame payload too short (< 4 bytes for cmdIdx)")
        }
        val cmdIdx = (frame.payload[0].toLong() and 0xFF) or
                ((frame.payload[1].toLong() and 0xFF) shl 8) or
                ((frame.payload[2].toLong() and 0xFF) shl 16) or
                ((frame.payload[3].toLong() and 0xFF) shl 24)

        if (cmdIdx != activeNextCmdIdx) {
            throw IllegalStateException("Unexpected cmdIdx in element $activeElementIndex: expected $activeNextCmdIdx, got $cmdIdx")
        }

        activeFragments.add(frame.payload.copyOfRange(4, frame.payload.size))
        activeNextCmdIdx++
    }

    private fun storeElement(index: Int, rawElement: ByteArray) {
        if (rawElement.size < ELEMENT_METADATA_SIZE) {
            throw IllegalStateException("Element $index too small (< $ELEMENT_METADATA_SIZE bytes)")
        }
        val jpegSlice = rawElement.copyOfRange(ELEMENT_METADATA_SIZE, rawElement.size)
        completedElements[index] = jpegSlice
    }

    fun buildJpeg(): ByteArray {
        val count = expectedElementCount ?: throw IllegalStateException("Element count not announced")
        if (!isComplete) {
            val missing = (1..count).filter { !completedElements.containsKey(it) }
            throw IllegalStateException("Cannot build JPEG, missing elements: $missing")
        }

        val out = ByteArrayOutputStream()
        for (i in 1..count) {
            val slice = completedElements[i] ?: error("Element $i missing")
            out.write(slice)
        }
        val image = out.toByteArray()

        if (image.size < 4) {
            throw IllegalStateException("Reassembled JPEG too short (${image.size} bytes)")
        }
        if (image[0] != JPEG_START[0] || image[1] != JPEG_START[1]) {
            throw IllegalStateException("Reassembled JPEG does not start with FFD8 (starts with %02X %02X)".format(image[0], image[1]))
        }
        if (image[image.size - 2] != JPEG_END[0] || image[image.size - 1] != JPEG_END[1]) {
            throw IllegalStateException("Reassembled JPEG does not end with FFD9 (ends with %02X %02X)".format(image[image.size - 2], image[image.size - 1]))
        }

        return image
    }
}
