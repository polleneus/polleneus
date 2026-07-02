package com.polleneus.client

import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test
import java.io.File

/**
 * The X4 copy-law gate: design-system §6's banned list, enforced over every string literal
 * in the client source tree (UI copy, notification copy, log lines — copy is copy).
 *
 * A hit is either a defect or a deliberate honest NEGATION ("There is no invisible mode."),
 * which must be allowlisted here explicitly, with the burden on the reviewer. This test is
 * a floor, not the audit: the human §3/§6 pass still runs on every PR.
 */
class CopyLawTest {

    /** Banned everywhere (brief §3, design system §6). Case-insensitive. */
    private val banned = listOf(
        Regex("""\banonymous\b""", RegexOption.IGNORE_CASE),
        Regex("""\banonymously\b""", RegexOption.IGNORE_CASE),
        Regex("""\banonymity\b""", RegexOption.IGNORE_CASE),
        Regex("""\buntraceable\b""", RegexOption.IGNORE_CASE),
        Regex("""\bundetectable\b""", RegexOption.IGNORE_CASE),
        Regex("""\binvisible\b""", RegexOption.IGNORE_CASE),
        Regex("""can'?not? be tracked""", RegexOption.IGNORE_CASE),
        Regex("""military[- ]grade""", RegexOption.IGNORE_CASE),
        Regex("""\bunbreakable\b""", RegexOption.IGNORE_CASE),
        Regex("""nsa[- ]proof""", RegexOption.IGNORE_CASE),
        Regex("""\bsecure\b""", RegexOption.IGNORE_CASE),      // unqualified "secure" is a claim
        Regex("""\bguaranteed?\b""", RegexOption.IGNORE_CASE),
        Regex("""\bdelivered\b""", RegexOption.IGNORE_CASE),
        Regex("""\bdelivery\b""", RegexOption.IGNORE_CASE),    // only honest negations may pass
        Regex("""\bonline\b""", RegexOption.IGNORE_CASE),      // presence doesn't exist here
        Regex("""\boffline\b""", RegexOption.IGNORE_CASE),
        Regex("""forward[- ]secre""", RegexOption.IGNORE_CASE), // FS is DEFERRED; no implication
    )

    /**
     * Honest negations / required disclosures, allowed by exact phrase AND file — an
     * exemption never leaks past the screen that earned it. Adding here is a copy-review
     * decision, not a convenience.
     */
    private val allowedPhrases = listOf(
        // onboarding deal row — the §3 must-disclose wording
        "OnboardingFlow.kt" to "There is no invisible mode.",
        // compose release button — negation of the promise, per design system §5
        "ComposeScreen.kt" to "no delivery promise",
        // local-hint label — "not delivery proof" is the §4-permitted phrasing
        "MessagesScreens.kt" to "not delivery proof",
        // contacts empty state — "presence doesn't exist here" (design system §5)
        "ContactsScreen.kt" to "no online/offline dots",
        // the canonical B3 not-protected row: delivery is disclosed as NOT protected
        "WhatThisProtectsScreen.kt" to "Delivery",
    )

    @Test
    fun `client copy contains no banned claims`() {
        val root = sourceRoot()
        val violations = mutableListOf<String>()

        root.walkTopDown().filter { it.isFile && it.extension == "kt" }.forEach { file ->
            val allowedHere = allowedPhrases.filter { it.first == file.name }.map { it.second }
            file.readLines().forEachIndexed { i, line ->
                for (literal in stringLiterals(line)) {
                    val cleaned = allowedHere.fold(literal) { acc, ok -> acc.replace(ok, "") }
                    for (rx in banned) {
                        val m = rx.find(cleaned)
                        if (m != null) {
                            violations += "${file.name}:${i + 1} banned \"${m.value}\" in: $literal"
                        }
                    }
                }
            }
        }

        if (violations.isNotEmpty()) {
            fail(
                "Copy-law violations (design system §6). Fix the copy or — for an honest " +
                    "negation only — allowlist the exact phrase:\n" +
                    violations.joinToString("\n"),
            )
        }
    }

    @Test
    fun `north star wording exists once and is shared, not paraphrased`() {
        // "Quote it, not paraphrase it" (design system §5): onboarding and the honesty screen
        // must render the same NorthStar composable — the canonical sentence lives in ONE place.
        val root = sourceRoot()
        val hits = root.walkTopDown()
            .filter { it.isFile && it.extension == "kt" }
            .filter { it.readText().contains("What you say, and who you say it to, are hidden.") }
            .map { it.name }
            .toList()
        assertTrue(
            "the canonical north-star sentence must live in exactly one file (found: $hits)",
            hits == listOf("OnboardingFlow.kt"),
        )
    }

    /**
     * String literals on one line; ignores line comments and KDoc/block-comment lines
     * (comments may quote banned words while explaining why they're banned).
     * Triple-quoted strings are not used in this codebase.
     */
    private fun stringLiterals(line: String): List<String> {
        val t = line.trimStart()
        if (t.startsWith("*") || t.startsWith("/*") || t.startsWith("//")) return emptyList()
        val code = line.substringBefore("//")
        val out = mutableListOf<String>()
        val rx = Regex(""""((?:[^"\\]|\\.)*)"""")
        rx.findAll(code).forEach { out += it.groupValues[1] }
        return out
    }

    private fun sourceRoot(): File {
        var dir = File(".").absoluteFile
        repeat(5) {
            val candidate = File(dir, "src/main/java/com/polleneus/client")
            if (candidate.isDirectory) return candidate
            val inApp = File(dir, "app/src/main/java/com/polleneus/client")
            if (inApp.isDirectory) return inApp
            dir = dir.parentFile ?: return@repeat
        }
        throw AssertionError("client source root not found from ${File(".").absolutePath}")
    }
}
