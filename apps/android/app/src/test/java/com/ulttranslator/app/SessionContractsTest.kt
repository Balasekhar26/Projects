package com.ulttranslator.app

import org.junit.Assert.assertEquals
import org.junit.Test

class SessionContractsTest {
    @Test
    fun defaultRequestMatchesSharedContractExpectations() {
        val request = StartSessionRequest()
        assertEquals("en", request.sourceLanguage)
        assertEquals("microphone", request.sessionKind)
        assertEquals("auto", request.onlinePolicy)
    }
}
