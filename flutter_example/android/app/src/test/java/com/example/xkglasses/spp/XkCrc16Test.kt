package com.example.xkglasses.spp

import org.junit.Assert.assertEquals
import org.junit.Test

class XkCrc16Test {

    @Test
    fun knownBind() {
        val p = "0100ffffffff0300000130303031003d00674b723934596642576a41443165634e31626d774d75387464444865414b5448375255683962736c736759474a6c74347a394359433775335861304e43"
            .chunked(2).map { it.toInt(16).toByte() }.toByteArray()
        assertEquals(0xed95, XkCrc16.compute(p))
    }

    @Test
    fun empty() {
        assertEquals(0xffff, XkCrc16.compute(ByteArray(0)))
    }
}
