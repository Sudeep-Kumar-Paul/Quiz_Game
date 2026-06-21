"""
QuizMaster - Flask Web App with Firebase + Polished UI
Run: python main.py
Open: http://localhost:3000

Firebase setup:
  pip install firebase-admin flask pyrebase4

Environment variables required:
  FIREBASE_API_KEY          – Web API key (from Firebase console → Project settings)
  FIREBASE_AUTH_DOMAIN      – e.g. your-project.firebaseapp.com
  FIREBASE_PROJECT_ID       – e.g. your-project
  FIREBASE_STORAGE_BUCKET   – e.g. your-project.appspot.com
  FIREBASE_MESSAGING_SENDER_ID
  FIREBASE_APP_ID
  GOOGLE_APPLICATION_CREDENTIALS – path to your serviceAccountKey.json (for Admin SDK)

Firestore collections used:
  leaderboard/  – one doc per entry, fields: name, uid, score, correct, total, category, pct, ts
  questions/    – one doc per category ("Science","Sports","GK"), field: items (array of question objects)
"""

import os, random, time
from flask import Flask, session, redirect, url_for, request
from dotenv import load_dotenv

load_dotenv()  # reads values from a local .env file (never committed to git)

# ─────────────────────────────────────────
#  🔧 FIREBASE CONFIG — loaded from environment variables.
#  Copy .env.example to .env and fill in your real values.
# ─────────────────────────────────────────
SERVICE_ACCOUNT_PATH = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "./serviceAccountKey.json")

FIREBASE_WEB_CONFIG = {
    "apiKey":            os.environ.get("FIREBASE_API_KEY"),
    "authDomain":        os.environ.get("FIREBASE_AUTH_DOMAIN"),
    "projectId":         os.environ.get("FIREBASE_PROJECT_ID"),
    "storageBucket":     os.environ.get("FIREBASE_STORAGE_BUCKET"),
    "messagingSenderId": os.environ.get("FIREBASE_MESSAGING_SENDER_ID"),
    "appId":             os.environ.get("FIREBASE_APP_ID"),
    "databaseURL":       os.environ.get("FIREBASE_DATABASE_URL", ""),
}

_missing = [k for k, v in FIREBASE_WEB_CONFIG.items() if not v and k != "databaseURL"]
if _missing or not os.path.exists(SERVICE_ACCOUNT_PATH):
    raise RuntimeError(
        "Missing Firebase config. Copy .env.example to .env, fill in your "
        "real Firebase values, and put your serviceAccountKey.json in the "
        "project root (it is git-ignored, so this is safe locally)."
    )
# ─────────────────────────────────────────

import firebase_admin
from firebase_admin import credentials, firestore

cred = credentials.Certificate(SERVICE_ACCOUNT_PATH)
firebase_admin.initialize_app(cred)
db = firestore.client()

import pyrebase

pb      = pyrebase.initialize_app(FIREBASE_WEB_CONFIG)
pb_auth = pb.auth()

# ─────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET")
if not app.secret_key:
    raise RuntimeError("Set FLASK_SECRET in your .env file (use a long random string).")

TIME_LIMIT      = 20
QUESTIONS_COUNT = 10
CAT_ICON        = {"Science": "⚛️", "Sports": "🏀", "GK": "🌐"}
CAT_CLASS       = {"Science": "cat-science", "Sports": "cat-sports", "GK": "cat-general"}

# ─────────────────────────────────────────
#  FALLBACK question bank
# ─────────────────────────────────────────
_FALLBACK_QUESTIONS = {
    "Science": [
        {"q": "What is the chemical symbol for water?",          "options": ["H2O","CO2","O2","NaCl"],              "ans": 0},
        {"q": "How many bones are in the adult human body?",     "options": ["206","186","226","196"],               "ans": 0},
        {"q": "What planet is known as the Red Planet?",         "options": ["Venus","Mars","Jupiter","Saturn"],     "ans": 1},
        {"q": "Approximate speed of light?",                     "options": ["3×10⁸ m/s","3×10⁶ m/s","3×10¹⁰ m/s","3×10⁴ m/s"], "ans": 0},
        {"q": "Which gas do plants absorb in photosynthesis?",   "options": ["Oxygen","Nitrogen","Carbon Dioxide","Hydrogen"], "ans": 2},
        {"q": "What is the powerhouse of the cell?",             "options": ["Nucleus","Ribosome","Mitochondria","Golgi body"], "ans": 2},
        {"q": "Atomic number of Carbon?",                        "options": ["6","8","12","14"],                    "ans": 0},
        {"q": "Who proposed the theory of general relativity?",  "options": ["Newton","Bohr","Einstein","Tesla"],   "ans": 2},
        {"q": "Hardest natural substance on Earth?",             "options": ["Iron","Quartz","Diamond","Graphite"], "ans": 2},
        {"q": "What type of wave is sound?",                     "options": ["Transverse","Longitudinal","Electromagnetic","Seismic"], "ans": 1},
        {"q": "Most abundant element in the universe?",          "options": ["Oxygen","Carbon","Helium","Hydrogen"],"ans": 3},
        {"q": "DNA stands for?",                                 "options": ["Deoxyribose Nucleic Acid","Deoxyribonucleic Acid","Dipeptide Nucleic Acid","Dinuclear Acid"], "ans": 1},
        {"q": "Unit of electric current?",                       "options": ["Volt","Watt","Ampere","Ohm"],         "ans": 2},
        {"q": "Which organ produces insulin?",                   "options": ["Liver","Kidney","Pancreas","Stomach"],"ans": 2},
        {"q": "Newton's first law is also called?",              "options": ["Law of Gravity","Law of Inertia","Law of Motion","Law of Entropy"], "ans": 1},
    ],
    "Sports": [
        {"q": "Players on a soccer team?",                       "options": ["9","10","11","12"],                   "ans": 2},
        {"q": "Which country invented cricket?",                 "options": ["India","Australia","England","South Africa"], "ans": 2},
        {"q": "Rings on the Olympic flag?",                      "options": ["4","5","6","7"],                      "ans": 1},
        {"q": "In tennis, zero is called?",                      "options": ["Nil","Zero","Love","Null"],           "ans": 2},
        {"q": "Most FIFA World Cup wins?",                       "options": ["Germany","Argentina","Italy","Brazil"],"ans": 3},
        {"q": "Length of a marathon?",                           "options": ["40 km","42.195 km","45 km","38 km"],  "ans": 1},
        {"q": "A basketball free throw is worth?",               "options": ["1 point","2 points","3 points","4 points"], "ans": 0},
        {"q": "Which sport uses a shuttlecock?",                 "options": ["Tennis","Squash","Badminton","Racquetball"], "ans": 2},
        {"q": "Holes in a standard golf course?",                "options": ["9","12","18","24"],                   "ans": 2},
        {"q": "National sport of Japan?",                        "options": ["Karate","Judo","Sumo","Baseball"],    "ans": 2},
        {"q": "Chess piece that moves only diagonally?",         "options": ["Rook","Knight","Bishop","Pawn"],      "ans": 2},
        {"q": "Volleyball players on court per team?",           "options": ["5","6","7","8"],                      "ans": 1},
        {"q": "Sport played at Wimbledon?",                      "options": ["Cricket","Badminton","Tennis","Squash"], "ans": 2},
        {"q": "Color of archery target center?",                 "options": ["Red","Blue","Yellow","Gold"],         "ans": 3},
        {"q": "Fastest swimming stroke?",                        "options": ["Backstroke","Breaststroke","Freestyle","Butterfly"], "ans": 2},
    ],
    "GK": [
        {"q": "Capital of Australia?",                           "options": ["Sydney","Melbourne","Canberra","Brisbane"], "ans": 2},
        {"q": "How many continents on Earth?",                   "options": ["5","6","7","8"],                      "ans": 2},
        {"q": "Largest ocean on Earth?",                         "options": ["Atlantic","Indian","Arctic","Pacific"],"ans": 3},
        {"q": "Who wrote Romeo and Juliet?",                     "options": ["Dickens","Shakespeare","Jane Austen","Homer"], "ans": 1},
        {"q": "Currency of Japan?",                              "options": ["Yuan","Won","Yen","Baht"],            "ans": 2},
        {"q": "Planet closest to the Sun?",                      "options": ["Venus","Earth","Mercury","Mars"],     "ans": 2},
        {"q": "Tallest mountain in the world?",                  "options": ["K2","Kangchenjunga","Lhotse","Mount Everest"], "ans": 3},
        {"q": "Colors in a rainbow?",                            "options": ["5","6","7","8"],                      "ans": 2},
        {"q": "Smallest country in the world?",                  "options": ["Monaco","San Marino","Vatican City","Liechtenstein"], "ans": 2},
        {"q": "Symbol Au stands for?",                           "options": ["Silver","Gold","Copper","Aluminium"], "ans": 1},
        {"q": "National animal of India?",                       "options": ["Lion","Elephant","Bengal Tiger","Leopard"], "ans": 2},
        {"q": "World War II ended in?",                          "options": ["1943","1944","1945","1946"],          "ans": 2},
        {"q": "Who painted the Mona Lisa?",                      "options": ["Michelangelo","Raphael","Leonardo da Vinci","Van Gogh"], "ans": 2},
        {"q": "Longest river in the world?",                     "options": ["Amazon","Mississippi","Yangtze","Nile"], "ans": 3},
        {"q": "Sides of a hexagon?",                             "options": ["5","6","7","8"],                      "ans": 1},
    ],
}

# ─────────────────────────────────────────
#  FIRESTORE helpers
# ─────────────────────────────────────────

def seed_questions_if_empty():
    col = db.collection("questions")
    for cat, items in _FALLBACK_QUESTIONS.items():
        doc = col.document(cat).get()
        if not doc.exists:
            col.document(cat).set({"items": items})
            print(f"  Seeded Firestore questions/{cat}")


def load_questions(category: str) -> list:
    doc = db.collection("questions").document(category).get()
    if doc.exists:
        return doc.to_dict().get("items", [])
    return _FALLBACK_QUESTIONS.get(category, [])


def load_lb() -> list:
    docs = (
        db.collection("leaderboard")
          .order_by("score", direction=firestore.Query.DESCENDING)
          .limit(15)
          .stream()
    )
    return [d.to_dict() for d in docs]


def add_entry(uid: str, name: str, score: int, correct: int, total: int, category: str):
    pct = round(correct / total * 100) if total else 0
    db.collection("leaderboard").add({
        "uid":      uid,
        "name":     name,
        "score":    score,
        "correct":  correct,
        "total":    total,
        "category": category,
        "pct":      pct,
        "ts":       firestore.SERVER_TIMESTAMP,
    })

# ─────────────────────────────────────────
#  AUTH helpers (Pyrebase)
# ─────────────────────────────────────────

def sign_up(email: str, password: str):
    return pb_auth.create_user_with_email_and_password(email, password)

def sign_in(email: str, password: str):
    return pb_auth.sign_in_with_email_and_password(email, password)

# ─────────────────────────────────────────
#  SHARED UI SHELL (dark aesthetic from quizmaster_final.html)
# ─────────────────────────────────────────

SHARED_STYLES = """
<style>
@keyframes floatIn{from{opacity:0;transform:translateY(-120px) rotate(var(--rs))}to{opacity:1;transform:translateY(0) rotate(var(--re))}}
@keyframes bob{0%,100%{transform:translateY(0)}50%{transform:translateY(14px)}}
@keyframes fadeIn{from{opacity:0}to{opacity:1}}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.5}}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0c0c0e;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px 12px;position:relative;overflow-x:hidden}
.bg-grad{position:fixed;inset:0;background:radial-gradient(ellipse at 15% 35%,rgba(80,90,200,.08) 0%,transparent 55%),radial-gradient(ellipse at 85% 65%,rgba(180,50,80,.07) 0%,transparent 55%);pointer-events:none;z-index:0}
.shapes{position:fixed;inset:0;overflow:hidden;pointer-events:none;z-index:0}
.sh{position:absolute;animation:floatIn 2.2s cubic-bezier(.23,.86,.39,.96) both}
.sh-inner{border-radius:9999px;border:1px solid rgba(255,255,255,.08);position:relative;overflow:hidden}
.sh-inner::after{content:'';position:absolute;inset:0;border-radius:9999px;background:radial-gradient(circle at 40% 40%,rgba(255,255,255,.07),transparent 65%)}
.bob{animation:bob 13s ease-in-out infinite}
.vign{position:fixed;inset:0;background:linear-gradient(to bottom,rgba(12,12,14,.8) 0%,transparent 20%,transparent 80%,rgba(12,12,14,1) 100%);pointer-events:none;z-index:0}
.page{position:relative;z-index:10;width:100%;max-width:680px;margin:0 auto;animation:fadeIn .35s ease both}

/* ── TYPOGRAPHY ── */
.grad-text{background:linear-gradient(90deg,#818cf8 0%,#fff 45%,#f9a8b8 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}
.grad-text2{background:linear-gradient(90deg,#818cf8,#f9a8b8);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}

/* ── BADGE ── */
.badge-pill{display:inline-flex;align-items:center;gap:7px;padding:5px 16px;border-radius:9999px;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.12);margin-bottom:1.5rem}
.badge-dot{width:7px;height:7px;border-radius:50%;background:#e8445a;flex-shrink:0}
.badge-pill span{font-size:12.5px;color:rgba(255,255,255,.5);letter-spacing:.05em}

/* ── CARD ── */
.card{width:100%;background:rgba(22,22,26,.9);border:1px solid rgba(255,255,255,.09);border-radius:16px;padding:1.5rem}
.card-lg{padding:2rem}

/* ── TAB BAR ── */
.tab-bar{display:grid;grid-template-columns:1fr 1fr;background:#161618;border:1px solid rgba(255,255,255,.07);border-radius:10px;padding:4px;margin-bottom:1.4rem;gap:3px}
.tab-btn{padding:10px 0;border-radius:7px;border:none;cursor:pointer;font-size:.88rem;font-weight:600;letter-spacing:.01em;transition:all .18s}
.tab-btn.off{background:transparent;color:rgba(255,255,255,.38)}
.tab-btn.on{background:linear-gradient(90deg,#6366f1,#ec4899);color:#fff}

/* ── FORM ── */
.f-label{font-size:.68rem;color:rgba(255,255,255,.35);letter-spacing:.1em;text-align:left;margin-bottom:.35rem;display:block}
.f-inp{width:100%;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.09);border-radius:8px;padding:11px 14px;color:rgba(255,255,255,.85);font-size:.88rem;outline:none;margin-bottom:1rem}
.f-inp::placeholder{color:rgba(255,255,255,.2)}
.f-inp:focus{border-color:rgba(99,102,241,.5)}

/* ── BUTTONS ── */
.btn-cta{width:100%;padding:14px;border-radius:10px;border:none;background:linear-gradient(90deg,#6366f1,#ec4899);color:#fff;font-size:.95rem;font-weight:700;cursor:pointer;letter-spacing:.02em;margin-top:.1rem;transition:opacity .2s}
.btn-cta:hover{opacity:.87}
.btn-ghost{display:inline-flex;align-items:center;gap:6px;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.09);border-radius:9999px;padding:5px 14px;color:rgba(255,255,255,.4);font-size:.82rem;cursor:pointer;transition:all .2s;text-decoration:none}
.btn-ghost:hover{color:rgba(255,255,255,.75)}
.btn-link{display:inline-flex;align-items:center;gap:7px;background:none;border:none;color:rgba(255,255,255,.35);font-size:.85rem;cursor:pointer;padding:0;text-decoration:none}
.btn-link:hover{color:rgba(255,255,255,.65)}

/* ── ALERT ── */
.alert{padding:10px 14px;border-radius:8px;font-size:.88rem;margin-bottom:1rem}
.alert-err{background:rgba(248,113,113,.08);color:#f87171;border:1px solid rgba(248,113,113,.25)}
.alert-ok{background:rgba(74,222,128,.08);color:#4ade80;border:1px solid rgba(74,222,128,.2)}

/* ── LOGIN PAGE ── */
.login-wrap{display:flex;flex-direction:column;align-items:center;text-align:center;max-width:480px;margin:0 auto;padding:1rem}
.login-h1{font-size:clamp(2.4rem,7vw,3.8rem);font-weight:700;line-height:1.08;letter-spacing:-.025em;margin-bottom:1rem;color:#fff}
.login-h1 .w2{display:block}
.login-sub{font-size:.88rem;color:rgba(255,255,255,.32);line-height:1.7;margin-bottom:2rem;max-width:360px}

/* ── DASHBOARD ── */
.dash-wrap{padding:1.5rem;max-width:860px;margin:0 auto;width:100%}
.dash-top{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:2rem}
.welcome-lbl{font-size:.78rem;color:rgba(255,255,255,.38);margin-bottom:.2rem}
.dash-h2{font-size:clamp(1.6rem,4vw,2.2rem);font-weight:700;letter-spacing:-.02em;color:#fff}
.dash-sub{font-size:.83rem;color:rgba(255,255,255,.3);margin-top:.5rem}
.logout-btn{display:inline-flex;align-items:center;gap:7px;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.1);border-radius:9999px;padding:7px 16px;color:rgba(255,255,255,.5);font-size:.83rem;cursor:pointer;transition:all .2s;text-decoration:none;white-space:nowrap}
.logout-btn:hover{background:rgba(255,255,255,.09);color:rgba(255,255,255,.8)}

/* ── CATEGORY GRID ── */
.cat-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-bottom:2rem}
@media(max-width:540px){.cat-grid{grid-template-columns:1fr}}
.cat-card{border-radius:14px;padding:1.5rem 1.3rem;cursor:pointer;border:1px solid rgba(255,255,255,.06);transition:transform .2s,border-color .2s;min-height:180px;display:flex;flex-direction:column;justify-content:space-between;text-decoration:none}
.cat-card:hover{transform:translateY(-3px);border-color:rgba(255,255,255,.18)}
.cat-science{background:linear-gradient(135deg,#0d4a52 0%,#0a2e3a 100%)}
.cat-sports{background:linear-gradient(135deg,#4a1a1a 0%,#2e0e0e 100%)}
.cat-general{background:linear-gradient(135deg,#2a1a4a 0%,#160e30 100%)}
.cat-icon-box{width:44px;height:44px;border-radius:10px;background:rgba(255,255,255,.12);display:flex;align-items:center;justify-content:center;margin-bottom:1.2rem;font-size:1.2rem}
.cat-name{font-size:1.05rem;font-weight:700;color:#fff;margin-bottom:.3rem}
.cat-count{font-size:.76rem;color:rgba(255,255,255,.45);margin-bottom:.9rem}
.cat-start{font-size:.8rem;color:rgba(255,255,255,.55)}

/* ── LEADERBOARD ── */
.lb-wrap{padding:1.5rem;max-width:680px;margin:0 auto;width:100%}
.lb-h1{font-size:clamp(1.9rem,5vw,2.7rem);font-weight:700;margin-bottom:.25rem}
.lb-tagline{font-size:.84rem;color:rgba(255,255,255,.3);margin-bottom:1.6rem}
.lb-row{display:flex;align-items:center;gap:14px;background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.07);border-radius:11px;padding:.85rem 1.15rem;margin-bottom:.6rem;transition:border-color .2s}
.lb-row:hover{border-color:rgba(255,255,255,.14)}
.lb-row.me{border-color:rgba(99,102,241,.4);background:rgba(99,102,241,.06)}
.lb-medal{font-size:1.3rem;flex-shrink:0;width:32px;text-align:center}
.lb-info{flex:1;min-width:0}
.lb-name{font-size:.92rem;font-weight:600;color:rgba(255,255,255,.88)}
.lb-meta{font-size:.73rem;color:rgba(255,255,255,.3);margin-top:2px}
.lb-right{text-align:right;flex-shrink:0}
.lb-pts{font-size:.94rem;font-weight:700}
.lb-pct{font-size:.72rem;color:rgba(255,255,255,.3);margin-top:2px}

/* ── QUIZ PAGE ── */
.quiz-wrap{padding:1.5rem;max-width:700px;margin:0 auto;width:100%}
.quiz-hdr{display:flex;justify-content:space-between;align-items:center;margin-bottom:14px}
.quiz-meta{font-size:.83rem;color:rgba(255,255,255,.4)}
.timer{font-size:1.05rem;font-weight:700;color:rgba(255,255,255,.8)}
.timer.urgent{color:#f87171;animation:pulse 1s ease infinite}
.prog-bar{height:5px;background:rgba(255,255,255,.08);border-radius:5px;margin-bottom:1.4rem;overflow:hidden}
.prog-fill{height:100%;background:linear-gradient(90deg,#6366f1,#ec4899);border-radius:5px;transition:width .4s}
.q-badge{display:inline-block;padding:3px 12px;border-radius:20px;font-size:.72rem;font-weight:600;background:rgba(99,102,241,.15);color:#a5b4fc;margin-bottom:.9rem}
.q-text{font-size:1.12rem;font-weight:600;line-height:1.55;color:#fff;margin-bottom:1.2rem}
.options{display:grid;gap:10px}
.opt{padding:13px 16px;background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.09);border-radius:10px;cursor:pointer;font-size:.95rem;display:flex;align-items:center;gap:12px;transition:.12s;color:rgba(255,255,255,.8);text-align:left;width:100%}
.opt:hover{border-color:rgba(99,102,241,.5);background:rgba(99,102,241,.08)}
.opt.correct{background:rgba(74,222,128,.07);border-color:rgba(74,222,128,.4);color:#4ade80}
.opt.wrong{background:rgba(248,113,113,.07);border-color:rgba(248,113,113,.4);color:#f87171}
.letter-box{width:28px;height:28px;border-radius:50%;background:rgba(255,255,255,.08);display:flex;align-items:center;justify-content:center;font-size:.78rem;font-weight:700;flex-shrink:0;color:rgba(255,255,255,.6)}
.feedback{margin-top:14px;padding:12px 16px;border-radius:9px;font-size:.93rem;font-weight:500}
.feedback.ok{background:rgba(74,222,128,.07);color:#4ade80;border:1px solid rgba(74,222,128,.2)}
.feedback.bad{background:rgba(248,113,113,.07);color:#f87171;border:1px solid rgba(248,113,113,.2)}
.score-line{margin-top:14px;color:rgba(255,255,255,.3);font-size:.83rem;text-align:center}
.score-line strong{color:#a5b4fc}

/* ── RESULT PAGE ── */
.result-wrap{padding:1.5rem;max-width:560px;margin:0 auto;width:100%;text-align:center}
.result-emoji{font-size:3.5rem;margin-bottom:.5rem}
.result-pts{font-size:2.6rem;font-weight:700;margin-bottom:.2rem}
.result-sub{font-size:.85rem;color:rgba(255,255,255,.35);margin-bottom:1.6rem}
.stat-row{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:1.4rem}
.stat{background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.07);border-radius:12px;padding:1rem}
.stat .num{font-size:1.6rem;font-weight:700;margin-bottom:.2rem}
.stat .lbl{font-size:.73rem;color:rgba(255,255,255,.35)}
.grade-card{background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.07);border-radius:12px;padding:1.2rem;margin-bottom:1.2rem;text-align:center}
.grade-label{font-size:1.05rem;font-weight:600;color:#fff;margin-bottom:.9rem}
.pct-bar-bg{background:rgba(255,255,255,.07);border-radius:8px;height:9px;overflow:hidden}
.pct-bar-fill{height:100%;border-radius:8px;transition:width .6s}
.pct-label{font-size:.78rem;color:rgba(255,255,255,.3);margin-top:6px}
.result-actions{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.btn-play{padding:13px;border-radius:10px;border:none;background:linear-gradient(90deg,#6366f1,#ec4899);color:#fff;font-size:.93rem;font-weight:700;cursor:pointer;text-decoration:none;display:block;text-align:center;transition:opacity .2s}
.btn-play:hover{opacity:.87}
.btn-lb{padding:13px;border-radius:10px;border:1px solid rgba(255,255,255,.12);background:rgba(255,255,255,.04);color:rgba(255,255,255,.7);font-size:.93rem;font-weight:600;cursor:pointer;text-decoration:none;display:block;text-align:center;transition:all .2s}
.btn-lb:hover{background:rgba(255,255,255,.08)}
</style>
"""

BG_HTML = """
<div class="bg-grad"></div>
<div class="shapes">
  <div class="sh" style="--rs:-3deg;--re:11deg;left:-7%;top:16%;animation-delay:.3s"><div class="sh-inner bob" style="width:500px;height:118px;background:linear-gradient(to right,rgba(80,100,200,.12),transparent);animation-delay:2.3s"></div></div>
  <div class="sh" style="--rs:0deg;--re:-14deg;right:-3%;top:66%;animation-delay:.5s"><div class="sh-inner bob" style="width:420px;height:100px;background:linear-gradient(to right,rgba(180,50,80,.1),transparent);animation-delay:2.8s"></div></div>
  <div class="sh" style="--rs:6deg;--re:-8deg;left:5%;bottom:9%;animation-delay:.4s"><div class="sh-inner bob" style="width:250px;height:66px;background:linear-gradient(to right,rgba(120,80,200,.1),transparent);animation-delay:2.6s"></div></div>
  <div class="sh" style="--rs:4deg;--re:19deg;right:14%;top:9%;animation-delay:.6s"><div class="sh-inner bob" style="width:165px;height:48px;background:linear-gradient(to right,rgba(180,140,40,.1),transparent);animation-delay:3s"></div></div>
  <div class="sh" style="--rs:-9deg;--re:-24deg;left:19%;top:5%;animation-delay:.7s"><div class="sh-inner bob" style="width:120px;height:33px;background:linear-gradient(to right,rgba(40,160,180,.1),transparent);animation-delay:3.1s"></div></div>
</div>
<div class="vign"></div>
"""


def page(title: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} — QuizMaster</title>
{SHARED_STYLES}
</head>
<body>
{BG_HTML}
<div class="page">
{body}
</div>
</body>
</html>"""


# ─────────────────────────────────────────
#  ROUTES
# ─────────────────────────────────────────

@app.route("/", methods=["GET", "POST"])
def login():
    error = ""
    if request.method == "POST":
        mode     = request.form.get("mode", "login")
        email    = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        name     = request.form.get("name", "").strip()

        try:
            if mode == "register":
                if not name:
                    raise ValueError("Display name is required.")
                user = sign_up(email, password)
                pb_auth.update_profile(user["idToken"], display_name=name)
                db.collection("users").document(user["localId"]).set({"name": name})
            else:
                user = sign_in(email, password)
                uid_info    = pb_auth.get_account_info(user["idToken"])
                stored_name = uid_info["users"][0].get("displayName", "")
                if not stored_name:
                    doc = db.collection("users").document(user["localId"]).get()
                    stored_name = doc.to_dict().get("name", "") if doc.exists else ""
                name = stored_name or email.split("@")[0]

            session["player"]   = name or email.split("@")[0]
            session["uid"]      = user["localId"]
            session["id_token"] = user["idToken"]
            return redirect(url_for("category"))

        except Exception as exc:
            msg = str(exc)
            print("AUTH ERROR:", msg)
            if "EMAIL_EXISTS" in msg:
                error = "That email is already registered. Please log in."
            elif "WEAK_PASSWORD" in msg:
                error = "Password must be at least 6 characters."
            elif "INVALID_PASSWORD" in msg or "INVALID_LOGIN_CREDENTIALS" in msg or "INVALID_EMAIL" in msg:
                error = "Incorrect email or password."
            elif "EMAIL_NOT_FOUND" in msg or "USER_NOT_FOUND" in msg:
                error = "No account found. Please register."
            elif "TOO_MANY_ATTEMPTS" in msg:
                error = "Too many attempts. Please wait a few minutes and try again."
            elif "MISSING_PASSWORD" in msg:
                error = "Please enter a password."
            else:
                error = f"Something went wrong: {msg[:300]}"

    error_html = f'<div class="alert alert-err">{error}</div>' if error else ""

    body = f"""
    <div class="login-wrap">
      <div class="badge-pill"><span class="badge-dot"></span><span>QuizMaster · Firebase</span></div>
      <h1 class="login-h1">Test your <span class="w2 grad-text">Knowledge</span></h1>
      <p class="login-sub">Beat the clock. Top the leaderboard. Three categories. Ten questions. Twenty seconds each.</p>
      <div class="card" style="width:100%;max-width:420px">
        <div class="tab-bar">
          <button class="tab-btn on"  id="tl" onclick="switchTab('login')">Log In</button>
          <button class="tab-btn off" id="tr" onclick="switchTab('register')">Register</button>
        </div>
        {error_html}

        <!-- LOGIN FORM -->
        <form method="POST" id="form-login">
          <input type="hidden" name="mode" value="login">
          <label class="f-label">EMAIL</label>
          <input class="f-inp" type="email" name="email" placeholder="you@example.com" required>
          <label class="f-label">PASSWORD</label>
          <input class="f-inp" type="password" name="password" placeholder="••••••••" required>
          <button class="btn-cta" type="submit">Log In →</button>
        </form>

        <!-- REGISTER FORM -->
        <form method="POST" id="form-register" style="display:none">
          <input type="hidden" name="mode" value="register">
          <label class="f-label">DISPLAY NAME</label>
          <input class="f-inp" type="text" name="name" placeholder="Your name" required>
          <label class="f-label">EMAIL</label>
          <input class="f-inp" type="email" name="email" placeholder="you@example.com" required>
          <label class="f-label">PASSWORD</label>
          <input class="f-inp" type="password" name="password" placeholder="Min 6 characters" required>
          <button class="btn-cta" type="submit">Create Account →</button>
        </form>
      </div>
      <div style="margin-top:1.5rem">
        <a class="btn-link" href="/leaderboard">🏆 View Leaderboard</a>
      </div>
    </div>
    <script>
      function switchTab(t){{
        var isLogin = t === 'login';
        document.getElementById('tl').className = 'tab-btn ' + (isLogin ? 'on' : 'off');
        document.getElementById('tr').className = 'tab-btn ' + (isLogin ? 'off' : 'on');
        document.getElementById('form-login').style.display    = isLogin ? '' : 'none';
        document.getElementById('form-register').style.display = isLogin ? 'none' : '';
      }}
    </script>"""
    return page("Login", body)


@app.route("/category")
def category():
    if not session.get("uid"):
        return redirect(url_for("login"))

    name = session["player"]
    cats = list(_FALLBACK_QUESTIONS.keys())

    cards_html = ""
    for cat in cats:
        qs    = load_questions(cat)
        icon  = CAT_ICON[cat]
        cls   = CAT_CLASS[cat]
        label = cat if cat != "GK" else "General Knowledge"
        cards_html += f"""
        <a class="cat-card {cls}" href="/start/{cat}">
          <div>
            <div class="cat-icon-box">{icon}</div>
            <div class="cat-name">{label}</div>
            <div class="cat-count">{len(qs)} questions</div>
          </div>
          <div class="cat-start">Start →</div>
        </a>"""

    body = f"""
    <div class="dash-wrap">
      <div class="dash-top">
        <div>
          <div class="welcome-lbl">Welcome back</div>
          <div class="dash-h2">Hey, <span class="grad-text2">{name}</span></div>
          <div class="dash-sub">Pick a category · {QUESTIONS_COUNT} random questions · {TIME_LIMIT}s per question</div>
        </div>
        <a class="logout-btn" href="/logout">↪ Logout</a>
      </div>
      <div class="cat-grid">{cards_html}</div>
      <div style="text-align:center">
        <a class="btn-link" href="/leaderboard">🏆 Leaderboard</a>
      </div>
    </div>"""
    return page("Choose Category", body)


@app.route("/start/<category>")
def start(category):
    if category not in _FALLBACK_QUESTIONS or not session.get("uid"):
        return redirect(url_for("category"))

    pool     = load_questions(category)
    selected = random.sample(pool, min(QUESTIONS_COUNT, len(pool)))

    session["quiz"] = {
        "category":   category,
        "questions":  selected,
        "current":    0,
        "score":      0,
        "correct":    0,
        "wrong":      0,
        "time_saved": 0,
    }
    return redirect(url_for("quiz"))


@app.route("/quiz", methods=["GET", "POST"])
def quiz():
    q_data = session.get("quiz")
    if not q_data or not session.get("uid"):
        return redirect(url_for("login"))

    questions = q_data["questions"]
    idx       = q_data["current"]

    if idx >= len(questions):
        return redirect(url_for("result"))

    q        = questions[idx]
    letters  = ["A", "B", "C", "D"]
    feedback = ""
    fb_class = ""

    if request.method == "POST":
        chosen  = request.form.get("answer", "")
        elapsed = float(request.form.get("elapsed", "20"))
        time_left = max(0, TIME_LIMIT - int(elapsed))

        if chosen.isdigit() and int(chosen) == q["ans"]:
            pts = 10 + time_left // 2
            q_data["score"]      += pts
            q_data["correct"]    += 1
            q_data["time_saved"] += time_left
        else:
            q_data["wrong"] += 1

        q_data["current"] += 1
        session["quiz"]    = q_data
        session.modified   = True

        if q_data["current"] >= len(questions):
            add_entry(
                uid=session["uid"], name=session["player"],
                score=q_data["score"], correct=q_data["correct"],
                total=len(questions), category=q_data["category"],
            )
            return redirect(url_for("result"))

        return redirect(url_for("quiz"))

    pct   = round(idx / len(questions) * 100)
    total = len(questions)
    cat   = q_data["category"]
    label = cat if cat != "GK" else "General Knowledge"

    options_html = ""
    for i, opt in enumerate(q["options"]):
        options_html += f"""
        <button class="opt" type="submit" name="answer" value="{i}">
          <span class="letter-box">{letters[i]}</span>{opt}
        </button>"""

    body = f"""
    <div class="quiz-wrap">
      <div class="quiz-hdr">
        <div class="quiz-meta">{CAT_ICON[cat]} {label} &nbsp;·&nbsp; Q{idx+1} of {total}</div>
        <div class="timer" id="timer">⏱ {TIME_LIMIT}s</div>
      </div>
      <div class="prog-bar"><div class="prog-fill" style="width:{pct}%"></div></div>
      <div class="card card-lg">
        <div class="q-badge">Question {idx+1} / {total}</div>
        <div class="q-text">{q["q"]}</div>
        <form method="POST" id="qform">
          <input type="hidden" name="elapsed" id="elapsed" value="0">
          <div class="options">{options_html}</div>
        </form>
        {f'<div class="feedback {fb_class}">{feedback}</div>' if feedback else ""}
      </div>
      <div class="score-line">Score so far: <strong>{q_data["score"]} pts</strong></div>
    </div>
    <script>
      var limit={TIME_LIMIT}, elapsed=0, interval;
      var timerEl=document.getElementById('timer');
      var elapsedInput=document.getElementById('elapsed');
      interval=setInterval(function(){{
        elapsed++;
        elapsedInput.value=elapsed;
        var left=limit-elapsed;
        timerEl.textContent='⏱ '+left+'s';
        if(left<=5) timerEl.classList.add('urgent');
        if(left<=0){{
          clearInterval(interval);
          elapsedInput.value=limit;
          var btn=document.createElement('input');
          btn.type='hidden'; btn.name='answer'; btn.value='-1';
          document.getElementById('qform').appendChild(btn);
          document.getElementById('qform').submit();
        }}
      }},1000);
      document.getElementById('qform').addEventListener('submit',function(){{
        clearInterval(interval);
      }});
    </script>"""
    return page("Quiz", body)


@app.route("/result")
def result():
    q_data = session.get("quiz")
    player = session.get("player")
    if not q_data or not player:
        return redirect(url_for("login"))

    score   = q_data["score"]
    correct = q_data["correct"]
    wrong   = q_data["wrong"]
    total   = correct + wrong
    saved   = q_data["time_saved"]
    cat     = q_data["category"]
    pct     = round(correct / total * 100) if total else 0

    if pct >= 90:   emoji, grade = "🏆", "Outstanding!"
    elif pct >= 70: emoji, grade = "🎉", "Great job!"
    elif pct >= 50: emoji, grade = "👍", "Good effort!"
    elif pct >= 30: emoji, grade = "📚", "Keep studying!"
    else:           emoji, grade = "😟", "Keep practicing!"

    if pct >= 70:   bar_color = "linear-gradient(90deg,#4ade80,#22d3ee)"
    elif pct >= 40: bar_color = "linear-gradient(90deg,#fbbf24,#f97316)"
    else:           bar_color = "linear-gradient(90deg,#f87171,#ec4899)"

    body = f"""
    <div class="result-wrap">
      <div class="result-emoji">{emoji}</div>
      <div class="result-pts grad-text2">{score} pts</div>
      <div class="result-sub">{pct}% accuracy · {cat if cat != "GK" else "General Knowledge"}</div>
      <div class="stat-row">
        <div class="stat"><div class="num" style="color:#4ade80">{correct}</div><div class="lbl">Correct</div></div>
        <div class="stat"><div class="num" style="color:#f87171">{wrong}</div><div class="lbl">Wrong</div></div>
        <div class="stat"><div class="num" style="color:#22d3ee">{saved}s</div><div class="lbl">Time Saved</div></div>
      </div>
      <div class="grade-card">
        <div class="grade-label">{grade}</div>
        <div class="pct-bar-bg">
          <div class="pct-bar-fill" style="width:{pct}%;background:{bar_color}"></div>
        </div>
        <div class="pct-label">{pct}% correct</div>
      </div>
      <div class="result-actions">
        <a class="btn-play" href="/category">🔄 Play Again</a>
        <a class="btn-lb"   href="/leaderboard">🏆 Leaderboard</a>
      </div>
    </div>"""
    return page("Result", body)


@app.route("/leaderboard")
def leaderboard():
    lb     = load_lb()
    player = session.get("player", "")
    medals = ["🥇", "🥈", "🥉"]

    rows = ""
    if not lb:
        rows = '<p style="color:rgba(255,255,255,.35);text-align:center;padding:28px">No scores yet — play a quiz!</p>'
    else:
        for i, e in enumerate(lb):
            rank     = medals[i] if i < 3 else f"#{i+1}"
            is_me    = e.get("name") == player
            cls      = "lb-row me" if is_me else "lb-row"
            cat_show = "General Knowledge" if e["category"] == "GK" else e["category"]
            me_tag   = " 👈" if is_me else ""
            rows += f"""
            <div class="{cls}">
              <div class="lb-medal">{rank}</div>
              <div class="lb-info">
                <div class="lb-name">{e["name"]}{me_tag}</div>
                <div class="lb-meta">{cat_show} · {e["correct"]}/{e["total"]} correct</div>
              </div>
              <div class="lb-right">
                <div class="lb-pts grad-text2">{e["score"]} pts</div>
                <div class="lb-pct">{e["pct"]}%</div>
              </div>
            </div>"""

    back = "/category" if player else "/"
    body = f"""
    <div class="lb-wrap">
      <a class="btn-ghost" href="{back}">‹ Back</a>
      <div style="margin-top:1rem">
        <div class="badge-pill"><span class="badge-dot"></span><span>Top 15</span></div>
      </div>
      <div class="lb-h1 grad-text2">Leaderboard</div>
      <div class="lb-tagline">The brightest minds. The fastest fingers.</div>
      {rows}
    </div>"""
    return page("Leaderboard", body)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ─────────────────────────────────────────
#  RUN
# ─────────────────────────────────────────
if __name__ == "__main__":
    seed_questions_if_empty()
    print("\n  🎯 QuizMaster is running!")
    print("  Open your browser → http://localhost:3000\n")
    app.run(debug=True, port=3000)
