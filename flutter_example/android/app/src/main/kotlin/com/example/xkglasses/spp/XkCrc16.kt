package com.example.xkglasses.spp

/**
 * CRC-16/CCITT-FALSE implementation matching the XK One Pro hardware protocol.
 * Polynomial: 0x1021, Init: 0xFFFF, Non-reflected, XOROut: 0x0000.
 */
object XkCrc16 {
    fun compute(bytes: ByteArray, offset: Int = 0, length: Int = bytes.size - offset): Int {
        var crc = 0xFFFF
        for (i in offset until (offset + length)) {
            crc = crc xor ((bytes[i].toInt() and 0xFF) shl 8)
            for (j in 0 until 8) {
                crc = if ((crc and 0x8000) != 0) {
                    ((crc shl 1) xor 0x1021) and 0xFFFF
                } else {
                    (crc shl 1) and 0xFFFF
                }
            }
        }
        return crc and 0xFFFF
    }
}
