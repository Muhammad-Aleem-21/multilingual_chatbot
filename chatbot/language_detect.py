"""
language_detect.py  -  "Which language did the user write in?"

The chatbot must understand 3 writing styles:

    english      ->  "Where is my order?"
    urdu         ->  "میرا آرڈر کہاں ہے؟"        (Urdu script)
    roman_urdu   ->  "mera order kahan hai"       (Urdu typed with English letters)

...and MIXES of them, e.g. "mera order track kar do please".

HOW THIS FILE WORKS (the simple idea)
-------------------------------------
1. Cut the message into words ("tokens").
2. Urdu script is easy: those letters live in a special Unicode range, so any
   word written with them is Urdu.
3. For words written in English letters we must decide: English or Roman Urdu?
   We keep two word lists:
       ENGLISH_WORDS      - common English words
       ROMAN_URDU_WORDS   - common Roman Urdu words, INCLUDING many spellings
                            ("kya", "kia", "kiya" / "hal", "haal" / "hai", "hy")
   If a word is in neither list we try a "fuzzy" match (catches typos like
   "delivry" or "kesay"). Words we cannot place are ignored.
4. Count the words of each kind and apply a simple reply rule (see below).

THE REPLY RULE
--------------
   * Look at the words that are Urdu or Roman Urdu ("local" words).
   * If local words are at least 40% of all recognised words (the number is
     LOCAL_SHARE_THRESHOLD in config.py), reply in the local language
     (Urdu script if there is more of it, otherwise Roman Urdu).
   * Otherwise reply in English.

This is a "rule-based" detector: no AI model, no internet, instant, and you can
read every decision. Its weakness: it only knows the words we put in the lists.
That is exactly why evaluation/eval_language_detection.py exists - it measures
how good the lists are, and you can add words to improve it.
"""

import difflib
import re
from dataclasses import dataclass, field
from typing import Optional

from chatbot.config import DEFAULT_LANGUAGE, LOCAL_SHARE_THRESHOLD

# ---------------------------------------------------------------------------
# WORD LISTS
# ---------------------------------------------------------------------------
# .split() turns a long string into a list of words; set(...) makes lookups fast.

ROMAN_URDU_WORDS = set("""
hai hy hain hen hun hoon ho hota hoti hote hua hui hue hogaya hogayi gaya gayi gaye gya gai
tha thi thay raha rahi rahe rha rhi rhe rehta rehti rehte reh rahta
mein mai mujhe mujhy mjhe mujhko mera meri mere meray mry mra
hum hamara hamari hamare tum tumhara tumhari aap ap aapka apka aapki apki aapke apke aapko apko
ye yeh wo woh usko isko iska uska unka inka apna apni apne khud
kya kia kiya kyaa kaise kese kaisay kesay kaisa kaisi kesa kesi
kahan kahaan kaha kidhar kahin kab kyun kyu kion kiu kyon kon kaun kaunsa konsa konsi kis kisne kisi
kitna kitne kitni kitnay kitany koi kuch kuchh kch
kar karo karna karni karen karein kare krna karta karti karte kardo kardein karun karoon karon karne
dein dena deni dijiye dijye diya dedo dedein
sakta sakti sakte skta sakein sakun sakoon
chahiye chahye chahiay chahyie chahie chahta chahti chahte chahiyay
milna mila mili mile milega milegi milenge milta milti
aya aaya aayi aai aaye aana aata aati aao aaj aj kal abhi abi ab tab jab tak tk
bhool bhol bhoolgaya bhula bhulgaya bhulgya
lagta lagti lagte lagna lagay lagen lag
batao bata batana batain bataein bataiye bataye btao btana
bhej bheja bhejo bhejdo bhijwa bhijwao
chal chalta chalti chalega chalo
dekho dekh dekhna dekhein dekhen dekhlo
samajh samjh maloom malum pata
lena lene liya liye lijiye
kaam
ka ki ke ko se sy say par pe pr ne bhi toh lekin magar aur ya kyunke kyunki agar phir fir
sirf bas bohat bohot bahut boht bht bahot zyada zyadah ziyada kam thora thoda jaldi jldi wapas wapis waapis
salam salaam assalam assalamualaikum assalamoalaikum aoa walaikum shukriya shukria shukrya meherbani mehrbani
maaf maafi khuda hafiz allah inshallah mashallah acha accha achha theek thik theak bilkul haan han jee ji
nahi nahin nai nhi nhn
paisa paise paisay rupay ghar din dino raat subah sham waqt jagah cheez saman samaan
kharab ghalat galat toota tuta tuti toot tooti
bhai bhaijan yaar yar dost sahab sahib baji apa behen oye arre wallah
wala wali wale jaisa jese jaise waisa isliye
rakho rakhna rakh
khatam shuru band khula khuli khulta baje ghante ghanta hafta haftay mahina mahine saal
sab sabhi sath saath liye kiye kiya kuchh
pohancha pohanch pahuncha pahunch pohnchi pohanchi pohanchay pohanche pahunchi
chalay chale
hojata hojaye hojayegi hojayega
ek sawal sawaal jawab jawaab madad masla mushkil baat
mil milay milen milein
""".split())

ENGLISH_WORDS = set("""
a an the is are was were be been am i me my mine you your yours he she it we they them his her our their
this that these those what when where which who whom why how can could will would shall should may might must
do does did done have has had not no yes and or but if so because as at by for from in into of on off to with without
about after before up down out over under again then there here please plz pls thanks thank thx hello hi hey ok okay sorry
want need like get got give tell know see check help send make take use work working works change cancel
order orders item items product products refund refunds return returns policy delivery deliver delivered payment pay paid
card cash account password email address number phone support customer care service hours time day days week weeks
money back wrong damaged broken received arrived arrive track tracking status code discount coupon long much many any some
all new old today tomorrow yesterday just now still yet already also too very more less same other another own only even
soon fast quickly reset delete update login log sign website app site online link process issue problem complaint price
charges free shipping exchange bank contact call talk speak reach open close available accept accepted methods method
kind type hold locked lock failed fail fails gone late delay delayed dont doesnt didnt cant wont isnt im ive whats hows thats
doing going come comes goes go let ask lost find found good great best nice bad thing things way place city
parcel package courier rider box size color colour stock available deliveries refunded replace replacement
processing process takes take takes taking usually normally minutes minute hour hours months month year years
mobile number name details detail info information question questions answer answers
one two three four five six seven eight nine ten
receive receiving ordered urgent last week hasnt havent hadnt werent wasnt arent
""".split())

# Pre-computed lists used for "fuzzy" matching (typo catching).
_ROMAN_LIST = sorted(ROMAN_URDU_WORDS)
_ENGLISH_LIST = sorted(ENGLISH_WORDS)

# ---------------------------------------------------------------------------
# TOKENISING
# ---------------------------------------------------------------------------
# Characters that belong to Urdu / Arabic script (Urdu is written with them).
_URDU_WORD_RE = re.compile(r"[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]+")
# English letters, optionally with an apostrophe inside (don't).
_LATIN_WORD_RE = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")


def _normalize_latin(word: str) -> str:
    """lower-case, drop apostrophes, squeeze long repeats: "Kyaaaa" -> "kya"."""
    word = word.lower().replace("'", "")
    return re.sub(r"(.)\1{2,}", r"\1", word)


def classify_latin_word(word: str) -> str:
    """Decide for ONE English-letter word: 'english', 'roman_urdu' or 'unknown'."""
    w = _normalize_latin(word)
    if w in ROMAN_URDU_WORDS:
        return "roman_urdu"
    if w in ENGLISH_WORDS:
        return "english"
    # Fuzzy matching: only for words with 4+ letters (short words give false hits).
    if len(w) >= 4:
        roman = difflib.get_close_matches(w, _ROMAN_LIST, n=1, cutoff=0.8)
        english = difflib.get_close_matches(w, _ENGLISH_LIST, n=1, cutoff=0.8)
        roman_score = difflib.SequenceMatcher(None, w, roman[0]).ratio() if roman else 0
        english_score = difflib.SequenceMatcher(None, w, english[0]).ratio() if english else 0
        if roman_score or english_score:
            # On a tie we prefer Roman Urdu (our spelling lists are the weaker side).
            return "roman_urdu" if roman_score >= english_score else "english"
    return "unknown"


# ---------------------------------------------------------------------------
# DETECTION
# ---------------------------------------------------------------------------
@dataclass
class Detection:
    label: str                      # english | urdu | roman_urdu | mixed | unknown
    reply_language: Optional[str]   # english | urdu | roman_urdu | None (= can't tell)
    counts: dict = field(default_factory=dict)   # how many words of each kind
    confidence: float = 0.0         # 0..1, how one-sided the message is

    @property
    def total_words(self) -> int:
        return sum(self.counts.values())


def detect_language(text: str) -> Detection:
    """Look at one message and say what language(s) it is written in."""
    # Urdu-script words: keep only tokens that contain at least one real letter
    # (this drops lone punctuation such as the Urdu question mark "؟").
    urdu_words = [w for w in _URDU_WORD_RE.findall(text) if any(ch.isalpha() for ch in w)]

    # Words in English letters: ask the lists what each one is.
    kinds = [classify_latin_word(w) for w in _LATIN_WORD_RE.findall(text)]

    counts = {
        "urdu": len(urdu_words),
        "roman_urdu": kinds.count("roman_urdu"),
        "english": kinds.count("english"),
    }
    urdu, roman, english = counts["urdu"], counts["roman_urdu"], counts["english"]
    local = urdu + roman
    total = local + english

    if total == 0:
        return Detection("unknown", None, counts, 0.0)

    # --- label: what kind of message is it? -------------------------------
    if (local > 0 and english > 0) or (urdu > 0 and roman > 0):
        label = "mixed"
    elif urdu > 0:
        label = "urdu"
    elif roman > 0:
        label = "roman_urdu"
    else:
        label = "english"

    # --- reply language: what should the bot answer in? --------------------
    local_share = local / total
    if local_share >= LOCAL_SHARE_THRESHOLD:
        reply = "urdu" if urdu >= roman else "roman_urdu"
    else:
        reply = "english"

    confidence = max(local_share, 1 - local_share)
    return Detection(label, reply, counts, round(confidence, 2))


# ---------------------------------------------------------------------------
# "Please reply in English" - the user can ask for a language explicitly
# ---------------------------------------------------------------------------
_REQUEST_VERBS = re.compile(
    r"\b(reply|answer|respond|speak|talk|write|type|jawab|javab|baat|bolo|likho|likhein|batao|samjhao)\b"
)
_LANGUAGE_PATTERNS = [   # order matters: "roman urdu" must be checked before "urdu"
    ("roman_urdu", r"roman[\s\-]*urdu|romanurdu"),
    ("urdu", r"\burdu\b"),
    ("english", r"\benglish\b|\bangrezi\b|\bangrezi\b"),
]


def detect_language_request(text: str) -> Optional[str]:
    """Did the user ask for a specific reply language? Returns it, or None.

    Examples that return a language:
        "please reply in English"          -> "english"
        "roman urdu mein jawab do"         -> "roman_urdu"
        "اردو میں جواب دیں"                  -> "urdu"
    """
    if "انگریزی میں" in text:
        return "english"
    if "اردو میں" in text:
        return "urdu"
    lowered = text.lower()
    for language, pattern in _LANGUAGE_PATTERNS:
        if not re.search(pattern, lowered):
            continue
        has_verb = _REQUEST_VERBS.search(lowered) is not None
        followed_by_mein = re.search(f"(?:{pattern})" + r"\s+(mein|me|mai|main)\b", lowered) is not None
        if has_verb or followed_by_mein:
            return language
    return None


# ---------------------------------------------------------------------------
# CONSISTENT REPLY LANGUAGE ACROSS A WHOLE CHAT
# ---------------------------------------------------------------------------
class LanguageTracker:
    """Remembers the language during a conversation so replies stay consistent.

    Three rules:
      1. If the user explicitly asks for a language, use it until they ask again.
      2. If a message has no recognisable words (e.g. "👍" or "12345"), keep using the
         previous language instead of guessing.
      3. If the chat is in Urdu / Roman Urdu and the user sends a tiny English
         message such as "ok" or "thanks", keep the previous language - a
         single polite word is not a language switch.
    """

    def __init__(self) -> None:
        self.current: Optional[str] = None   # language used for the last reply
        self.forced: Optional[str] = None    # language the user explicitly asked for

    def update(self, text: str) -> str:
        """Call once per user message. Returns the language the bot must reply in."""
        requested = detect_language_request(text)
        if requested:
            self.forced = requested
            self.current = requested
            return requested

        if self.forced:
            return self.forced

        detection = detect_language(text)

        if detection.reply_language is None:                      # rule 2
            return self.current or DEFAULT_LANGUAGE

        is_tiny_english = detection.label == "english" and detection.total_words <= 2
        if is_tiny_english and self.current in ("urdu", "roman_urdu"):   # rule 3
            return self.current

        self.current = detection.reply_language
        return self.current
