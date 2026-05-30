"""
PMC Engine — Hybrid Intent Parser (Layer 2)
============================================
Classifies query intent using a hybrid approach:
  - Fast path: regex rules (<1ms, 70-80% accurate)
  - Slow path: MiniLM embeddings (~20ms, 90%+ accurate, optional)
  - Fallback: UNKNOWN → conservative mode (more context)
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ─── Enums ──────────────────────────────────────────────────────────────────

class OpType(str, Enum):
    MODIFY   = "MODIFY"
    CREATE   = "CREATE"
    READ     = "READ"
    DEBUG    = "DEBUG"
    REFACTOR = "REFACTOR"
    TEST     = "TEST"
    UNKNOWN  = "UNKNOWN"

class BlastRadius(str, Enum):
    LOW    = "LOW"
    MEDIUM = "MEDIUM"
    HIGH   = "HIGH"


# ─── Output ─────────────────────────────────────────────────────────────────

@dataclass
class ParsedIntent:
    op_type: OpType
    target_syms: list[str]
    blast_radius: BlastRadius
    priority_terms: list[str]
    raw_query: str
    context_budget: int = 4000
    confidence: float = 1.0  # 0.0 (unsure) to 1.0 (very sure)
    extraction_warnings: list[str] = field(default_factory=list)


# ─── Rules ──────────────────────────────────────────────────────────────────

_OP_PATTERNS: list[tuple[OpType, list[str]]] = [
    (OpType.DEBUG, [
        r"\bfix\b", r"\bbug\b", r"\berror\b", r"\bcrash\b", r"\bfails?\b",
        r"\bbroken\b", r"\brace condition\b", r"\bnull pointer\b",
        r"\bexception\b", r"\btraceback\b", r"\bwhy (is|does|isn\'t)\b",
        r"\bdebug\b", r"\bissue\b", r"\bproblem\b", r"\bbad\b",
        r"\bnot working\b", r"\bincorrect\b", r"\bregression\b",
    ]),
    (OpType.CREATE, [
        r"\badd\b", r"\bcreate\b", r"\bimplement\b", r"\bbuild\b",
        r"\bnew (function|method|class|endpoint|feature|route|api)\b",
        r"\bwrite\b", r"\bgenerate\b", r"\bscaffold\b",
    ]),
    (OpType.REFACTOR, [
        r"\brefactor\b", r"\bclean.?up\b", r"\bextract\b", r"\bmove\b",
        r"\brename\b", r"\bsplit\b", r"\bdecompose\b", r"\bsimplify\b",
        r"\boptimize\b", r"\bperformance\b", r"\bimprove\b",
        r"\brestructure\b", r"\breorganize\b", r"\bmodularize\b",
    ]),
    (OpType.TEST, [
        r"\btest\b", r"\bspec\b", r"\bunit test\b", r"\bmock\b",
        r"\bcoverage\b", r"\bassert\b", r"\bpytest\b", r"\bjest\b",
        r"\bqa\b", r"\bquality\b",
    ]),
    (OpType.READ, [
        r"\bexplain\b", r"\bhow does\b", r"\bwhat (is|does|are)\b",
        r"\bunderstand\b", r"\bshow me\b", r"\btrace\b", r"\bwalk.?through\b",
        r"\bdescribe\b", r"\bwhere is\b", r"\bfind\b", r"\bdocument\b",
    ]),
    (OpType.MODIFY, [
        r"\bchange\b", r"\bupdate\b", r"\bmodify\b", r"\bedit\b",
        r"\balter\b", r"\badjust\b", r"\btweak\b", r"\bpatch\b",
        r"\bswitch\b", r"\breplace\b", r"\tconvert\b",
    ]),
]

_HIGH_BLAST_TERMS = [
    r"\bauth(entication)?\b", r"\bsession\b", r"\btoken\b",
    r"\bdatabase\b", r"\bmiddleware\b", r"\bconfig\b", r"\bbase class\b",
    r"\bshared\b", r"\bglobal\b", r"\bapi\b", r"\brouter\b",
    r"\ball (user|request|endpoint)s?\b",
    r"\bsecurity\b", r"\bpermissions?\b", r"\blogin\b",
]

_IDENTIFIER = re.compile(r'\b([a-z_][a-z0-9_]{2,})\b', re.IGNORECASE)

_STOPWORDS = {
    "the", "fix", "add", "use", "get", "set", "let", "run", "can",
    "for", "and", "with", "that", "this", "from", "into", "when",
    "after", "before", "should", "make", "sure", "have", "also",
    "where", "which", "there", "here", "what", "how", "does", "will",
    "not", "but", "was", "its", "our", "you", "any", "all", "new",
    "rate", "race", "bug", "error", "issue", "code", "file", "test",
    "class", "function", "method", "line", "flow", "endpoint",
    "need", "try", "see", "now", "yet", "just", "way", "say",
}

# Terms that signal high confidence the intent is clear
_HIGH_CONFIDENCE_TERMS = [
    r"\bfix\b", r"\bchange\b", r"\badd\b", r"\bcreate\b",
    r"\bexplain\b", r"\brefactor\b",
]


class IntentParser:
    """
    Hybrid intent parser. Fast regex path first; falls back to
    embedding-based classification (optional sentence-transformers).

    Designed to be fast (no LLM call) — runs in <1ms for regex path.
    """

    def __init__(self, use_embeddings: bool = False):
        self.use_embeddings = use_embeddings
        self._embedder = None

    def parse(self, query: str, known_symbols: Optional[set[str]] = None) -> ParsedIntent:
        q = query.strip()
        q_lower = q.lower()

        # Fast path: regex rules
        op_type, confidence = self._classify_op(q_lower)
        target_syms = self._extract_symbols(q, known_symbols or set())
        blast_radius = self._estimate_blast(q_lower, op_type, target_syms)
        priority_terms = self._extract_priority_terms(q_lower, op_type)
        context_budget = self._budget_for(op_type, blast_radius)

        # If low confidence and embeddings available, try slow path
        warnings = []
        if confidence < 0.5 and self.use_embeddings:
            try:
                better_op = self._classify_with_embeddings(q_lower)
                if better_op != OpType.UNKNOWN:
                    op_type = better_op
                    confidence = 0.7
                    context_budget = self._budget_for(op_type, blast_radius)
            except Exception:
                pass

        if confidence < 0.4:
            # Low confidence — warn downstream to use conservative mode
            warnings.append("Low confidence in intent classification — using conservative mode")
            blast_radius = BlastRadius.HIGH  # more context when unsure
            context_budget = self._budget_for(op_type, blast_radius)

        return ParsedIntent(
            op_type=op_type,
            target_syms=target_syms,
            blast_radius=blast_radius,
            priority_terms=priority_terms,
            raw_query=q,
            context_budget=context_budget,
            confidence=confidence,
            extraction_warnings=warnings,
        )

    # ── Fast Path: Regex ───────────────────────────────────────────────────

    def _classify_op(self, q_lower: str) -> tuple[OpType, float]:
        scores: dict[OpType, int] = {op: 0 for op, _ in _OP_PATTERNS}

        for op_type, patterns in _OP_PATTERNS:
            for pat in patterns:
                if re.search(pat, q_lower):
                    scores[op_type] += 1

        if not any(scores.values()):
            return OpType.UNKNOWN, 0.0

        priority = [OpType.DEBUG, OpType.MODIFY, OpType.CREATE,
                    OpType.READ, OpType.REFACTOR, OpType.TEST]
        best_score = max(scores.values())
        for op in priority:
            if scores.get(op, 0) == best_score:
                # Calculate confidence: ratio of matched patterns to total
                total_patterns = sum(len(p) for _, p in _OP_PATTERNS if _[0] == op)
                confidence = min(best_score / max(total_patterns, 1) * 3, 0.95)
                # Boost if query contains high-confidence terms
                if any(re.search(t, q_lower) for t in _HIGH_CONFIDENCE_TERMS):
                    confidence = min(confidence + 0.15, 0.98)
                return op, round(confidence, 2)

        return OpType.UNKNOWN, 0.0

    # ── Slow Path: Embeddings (optional) ──────────────────────────────────

    def _classify_with_embeddings(self, q_lower: str) -> OpType:
        """Use sentence-transformers for intent classification."""
        try:
            from sentence_transformers import SentenceTransformer, util

            if self._embedder is None:
                self._embedder = SentenceTransformer("all-MiniLM-L6-v2")

            # Labeled examples for each op type
            examples = {
                OpType.DEBUG: [
                    "fix the bug in login", "why is this crashing",
                    "the test is failing", "error in user creation",
                    "race condition in auth",
                ],
                OpType.MODIFY: [
                    "change the password hashing", "update the rate limit",
                    "modify the user model", "edit the config value",
                    "switch from JWT to OAuth",
                ],
                OpType.CREATE: [
                    "add a new endpoint", "implement user registration",
                    "build a notification system", "create a new model",
                    "write a database migration",
                ],
                OpType.READ: [
                    "explain how login works", "what does this function do",
                    "show me the user schema", "describe the auth flow",
                    "find where tokens are generated",
                ],
                OpType.REFACTOR: [
                    "refactor the auth module", "clean up the database layer",
                    "extract the validation logic", "optimize the query",
                    "simplify the error handling",
                ],
                OpType.TEST: [
                    "write unit tests for login", "add test coverage",
                    "mock the database in tests", "create a test fixture",
                    "verify the authentication flow",
                ],
            }

            query_emb = self._embedder.encode(q_lower, convert_to_tensor=True)
            best_sim = 0.0
            best_op = OpType.UNKNOWN

            for op_type, texts in examples.items():
                text_embs = self._embedder.encode(texts, convert_to_tensor=True)
                sim = util.cos_sim(query_emb, text_embs).max().item()
                if sim > best_sim:
                    best_sim = sim
                    best_op = op_type

            return best_op if best_sim > 0.5 else OpType.UNKNOWN
        except ImportError:
            return OpType.UNKNOWN
        except Exception:
            return OpType.UNKNOWN

    # ── Symbol Extraction ──────────────────────────────────────────────────

    def _extract_symbols(self, query: str, known_symbols: set[str]) -> list[str]:
        candidates = []
        definite = []

        for m in _IDENTIFIER.finditer(query):
            word = m.group(1)
            if word in known_symbols:
                definite.append(word)
            elif ("_" in word or word[0].isupper()
            ) and word.lower() not in _STOPWORDS:
                candidates.append(word)

        seen = set()
        result = []
        for s in definite + candidates:
            if s not in seen:
                seen.add(s)
                result.append(s)
        return result[:8]

    # ── Blast / Budget ─────────────────────────────────────────────────────

    def _estimate_blast(self, q_lower: str, op_type: OpType, targets: list[str]) -> BlastRadius:
        if op_type in (OpType.READ,):
            return BlastRadius.LOW

        high_signal = any(re.search(p, q_lower) for p in _HIGH_BLAST_TERMS)
        if high_signal:
            return BlastRadius.HIGH

        if op_type == OpType.REFACTOR:
            return BlastRadius.MEDIUM

        if len(targets) >= 3:
            return BlastRadius.MEDIUM

        return BlastRadius.LOW

    def _extract_priority_terms(self, q_lower: str, op_type: OpType) -> list[str]:
        stopwords = {
            "fix", "add", "create", "implement", "explain", "how", "does",
            "update", "change", "modify", "the", "and", "for", "with",
            "function", "method", "class", "in", "to", "a", "of", "on",
            "is", "it", "at", "by", "an", "or", "as", "be", "this", "that",
        }
        words = q_lower.split()
        return [w for w in words if len(w) > 3 and w not in stopwords][:12]

    def _budget_for(self, op_type: OpType, blast: BlastRadius) -> int:
        base = {
            OpType.READ:     1500,
            OpType.DEBUG:    3500,
            OpType.MODIFY:   3000,
            OpType.CREATE:   2500,
            OpType.REFACTOR: 4000,
            OpType.TEST:     2000,
            OpType.UNKNOWN:  4000,  # more budget when unsure
        }[op_type]

        multiplier = {
            BlastRadius.LOW:    1.0,
            BlastRadius.MEDIUM: 1.5,
            BlastRadius.HIGH:   2.0,
        }[blast]

        return int(base * multiplier)
