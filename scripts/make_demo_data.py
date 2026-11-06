"""Generate realistic synthetic WhatsApp exports (fictional people) for development and the demo.

    python scripts/make_demo_data.py

Writes data/demo/:
  WhatsApp Chat with College Friends.zip       Android export with media, 20 members, Feb 2025 to Jan 2026
  no-media/WhatsApp Chat with College Friends.txt   the same chat exported without media
  WhatsApp Chat - Shrimant.zip                 iOS export with media, one-to-one
  facts.json                                   what is planted in the data, for tests and evals
"""
from __future__ import annotations

import io
import json
import random
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "demo"
rng = random.Random(7)
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

ME = "Suman Ghosh"
GROUP = "College Friends"
FRIEND = "Shrimant"
TANIA = "+91 98311 45678"  # not saved in the exporter's contacts, so the export shows the number


@dataclass
class Media:
    kind: str  # image | voice | video | sticker | document
    spec: dict
    name: str = ""


@dataclass
class Msg:
    ts: datetime
    sender: str | None  # None = system line
    text: str = ""
    media: Media | None = None
    edited: bool = False
    deleted: bool = False


# name: (message weight, conversation-start weight, gender for the voice)
CAST = {
    "Priya Sen": (13, 30, "Female"), "Rohan Das": (10, 6, "Male"), ME: (10, 9, "Male"),
    "Arjun Mehta": (9, 7, "Male"), "Kabir Malhotra": (7, 5, "Male"), "Sayan Mukherjee": (6, 4, "Male"),
    "Ananya Roy": (6, 4, "Female"), "Ishita Banerjee": (5, 3, "Female"), "Abhishek Kundu": (6, 3, "Male"),
    "Meera Iyer": (4, 3, "Female"), "Nikhil Sharma": (4, 2, "Male"), "Riya Dutta": (3, 2, "Female"),
    "Tanvi Kapoor": (3, 2, "Female"), "Vikram Singh": (3, 2, "Male"), "Sneha Paul": (3, 1, "Female"),
    "Pooja Agarwal": (2, 1, "Female"), "Rahul Verma": (2, 1, "Male"), "Aditya Bose": (3, 2, "Male"),
    TANIA: (2, 1, "Female"), "Dev Chatterjee": (0.3, 0, "Male"),
}

# month: (mood pool, activity, topic lines)
MONTHS = {
    (2025, 2): ("pos", 0.9, ["new sem new me 😤", "timetable aa gaya", "canteen ka naya momo try kiya?", "Saraswati Puja pe kya pehen rahe ho?"]),
    (2025, 3): ("pos", 1.4, ["Goa countdown 🏖️", "sunscreen le lena sab", "Baga ya Calangute?", "Goa ke photos abhi tak edit nahi hue", "Goa 2.0 kab?"]),
    (2025, 4): ("pos", 1.0, ["Goa hangover abhi bhi hai", "seniors ka farewell plan karna hai", "KKR ka match aaj, Eden chalein?", "IPL dekh raha koi?"]),
    (2025, 5): ("neg", 1.3, ["DBMS normalization samjha de koi", "OS ke notes kiske paas?", "CN viva kab hai", "exam ke baad party pakka"]),
    (2025, 6): ("neu", 0.6, ["result aaya?", "summer mein ghar ja raha hoon", "itni garmi hai Kolkata mein 🥵", "monsoon kab aayega yaar"]),
    (2025, 7): ("neu", 0.8, ["internship mil gayi kisi ko?", "WFH internship hai mera", "resume review kar dega koi?", "Darjeeling plan karein August mein?"]),
    (2025, 8): ("neg", 1.0, ["Darjeeling ka kya hua?", "group itna quiet kyun hai", "sab theek hai na?", "koi baat nahi karna chahta kya"]),
    (2025, 9): ("pos", 1.4, ["Puja aa gayi 🥁", "naye kapde liye?", "Sashthi ko kahan milna hai", "Mahalaya ki recording subah sunni hai"]),
    (2025, 10): ("pos", 1.2, ["Ashtami anjali saath chalein?", "Dashami pe sindoor khela dekhna hai", "Puja khatam, depression shuru 😭", "Kali Puja pandal dekhne chalein"]),
    (2025, 11): ("neg", 0.9, ["placement drive kal se", "aptitude test kaisa gaya", "HR round mein kya pucha?", "DSA revise kar raha hoon raat bhar"]),
    (2025, 12): ("pos", 1.1, ["placement party kab de raha?", "Park Street lights dekhne chalein 24 ko", "Flurys ka plum cake 🎄", "New year plan kya hai?"]),
    (2026, 1): ("pos", 0.9, ["farewell ki planning start", "last sem hai yaar 🥲", "yearbook ke liye photos bhejo", "Goa 2.0 reunion pakka karein?"]),
}

SHORT = ["haha", "😂😂😂", "lol", "sahi hai", "same", "bro 💀", "kya baat", "pakka", "ok done", "hmm", "👍", "true", "facts",
         "arre", "kab?", "kahan?", "chal", "bhai 😭", "ekdum", "accha", "theek hai", "omg", "noo", "yesss", "haan", "nahi yaar"]
POOLS = {
    "pos": ["aaj ka din ekdum mast tha", "canteen mein milte 5 baje?", "bhai photos bhejo sab", "kal ka plan pakka na?",
            "kya scene tha yaar 😂", "ye group best hai honestly", "Park Street chalein weekend?", "Coffee House mein adda 4 baje?",
            "bro tu legend hai", "aaj raat movie?", "puchka khane chalein College Street?", "mood ekdum fresh hai",
            "photos dekh ke hasi ruk nahi rahi", "ye wala pic DP banega pakka", "kal class bunk karke Victoria?", "best day of the sem tbh"],
    "neg": ["kuch padha nahi hai yaar", "kal ka paper toh gaya", "neend nahi aa rahi tension mein", "attendance shortage aa gaya mera",
            "syllabus khatam hi nahi ho raha", "aaj ka din bekar tha", "sab log itne quiet kyun ho", "mera mood off hai, baad mein baat karte",
            "honestly thak gaya hoon", "ye sem kab khatam hoga", "result ka darr lag raha", "aaj canteen bhi band tha 😑"],
    "neu": ["kal class hai kya?", "assignment ki deadline kab hai?", "kaun kaun aa raha kal?", "sir ne mail bheja dekha?",
            "lab record submit kiya?", "library ka wifi password kya hai", "kal ka timetable bhejo", "LinkedIn pe connect kar lo sab",
            "aaj late hoga thoda", "metro mein hoon, 20 min", "kal 10 baje milte gate pe", "Salt Lake jaana hai kal"],
}
SAYAN_LONG = [
    "Honestly I think we should decide things earlier as a group. Every time we plan last minute, half of us can't come and then everyone feels bad. Point being, let's fix dates one week before.",
    "I was thinking about this. We keep saying we'll study together but we end up talking for three hours. Not complaining, it's the best part of my day, but maybe one hour of work first?",
    "Okay small observation. This group is most active between 11 pm and 1 am, which explains why all of us are sleepy in the 9 am class. Just saying.",
    "For the record, I did the maths and we have spent more on Coffee House this semester than on books. I am not judging. I am also part of the problem.",
]
ROHAN_VN = [
    "ek minute ek minute, sun na, kal canteen mein jo hua woh main bata hi nahi paaya, bahut funny tha",
    "ek minute, bas ek minute, assignment ka deadline extend ho gaya hai, sir ne abhi bola",
    "arre sun na, main metro mein hoon, network nahi hai, pahunch ke call karta hoon",
    "bhai haan haan main aa raha hoon, bas dus minute, ekdum dus minute",
    "ek minute, mujhe lagta hai hum log ko is weekend kuch plan karna chahiye, kya bolte ho sab",
    "sun, aaj professor ne attendance li aur main proxy nahi laga paaya, sorry yaar",
    "ek minute, ye wala meme dekh ke main hans hans ke mar gaya, Arjun tu legend hai",
    "acha sun, kal ka plan cancel mat karna, main pakka aa raha hoon is baar",
    "bhai mera phone ka charger kisi ke paas hai kya, main library mein hoon",
    "ek minute, Priya ne jo bola woh sahi hai, hum log ko pehle se book karna chahiye",
]
OTHER_VN = ["haan main aa rahi hoon, bas paanch minute", "sun na, notes bhej de please", "main abhi bus mein hoon, baad mein baat karte hain",
            "kal ka plan pakka hai na, confirm kar do"]
EMOJI = ["😂", "💀", "🔥", "😭", "🙌", "🤣", "😎", "🥳"]
JOKES = {  # phrase: (available from, lines that reuse it)
    "3 baje Maggi": (datetime(2025, 3, 16, 3, 10), ["aaj phir 3 baje Maggi?", "3 baje Maggi squad assemble 🍜", "Kabir ka 3 baje Maggi wala scene 😂"]),
    "ek minute": (datetime(2025, 2, 20, 21, 45), ["Rohan ka 'ek minute' matlab 5 minute voice note 😭", "bhai ek minute mat bolna please 💀", "ek minute bolke 4 min ka VN bheja phir se"]),
    "PPT bana de": (datetime(2025, 4, 10, 21, 35), ["Sayan PPT bana de iska bhi 😂", "decide karne ke liye Sayan PPT bana dega", "PPT bana de bhai, phir vote karte"]),
}
MEMES = [  # (top, bottom, available from)
    ("when Rohan says 'ek minute'", "*sends a 4 minute voice note*", datetime(2025, 2, 21)),
    ("me before exams", "me after exams", None), ("attendance 74%", "sir please 1%", None),
    ("3 AM in the hostel", "3 baje Maggi", datetime(2025, 3, 17)), ("Sayan before every decision", "let me make a PPT", datetime(2025, 4, 11)),
    ("Priya:", "guys plan final karte hain", None), ("Monday 9 am class", "bunk", None), ("placement season", "DSA at 2 am", datetime(2025, 11, 1)),
]


def t(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d %H:%M")


def img(lines=None, scene=None, caption=None, header=None, accent="#2b6cb0"):
    return Media("image", {"lines": lines, "scene": scene, "caption": caption, "header": header, "accent": accent})


def vn(text):
    return Media("voice", {"text": text})


# ----------------------------------------------------------------------------- group beats
def group_beats() -> list[Msg]:
    B = []

    def b(ts, sender, text="", media=None):
        B.append(Msg(t(ts), sender, text, media))

    b("2025-02-03 19:30", None, "Messages and calls are end-to-end encrypted. Only people in this chat can read, listen to, or share them. Learn more.")
    b("2025-02-03 19:30", None, f'Priya Sen created group "{GROUP}"')
    b("2025-02-03 19:30", None, "Priya Sen added You")
    for name in CAST:
        if name not in ("Priya Sen", ME):
            b("2025-02-03 19:31", None, f"Priya Sen added {name}")
    b("2025-02-03 19:33", "Priya Sen", "Welcome sab ko 🎉 ye group sirf hum logon ka, no seniors no profs")
    b("2025-02-03 19:35", "Rohan Das", media=vn("ek minute ek minute, sab sun lo, is group ka naam College Friends hi rahega, koi change nahi karega, theek hai"))
    b("2025-02-03 19:36", "Arjun Mehta", "finally ek group without seniors 😂🔥")
    b("2025-02-14 22:10", "Kabir Malhotra", "single logon ka group ban gaya ye 💀")
    b("2025-02-20 21:40", "Rohan Das", media=vn("ek minute, bas ek minute, kal ke DBMS lab mein jo sir ne bola na, woh actually exam mein aayega, sab dhyan se sunna"))
    b("2025-02-20 21:44", "Abhishek Kundu", "Rohan bhai tera 'ek minute' matlab 4 minute ka voice note 😭")
    b("2025-02-20 21:45", "Arjun Mehta", "ek minute 💀💀")

    # March: Goa
    b("2025-03-01 20:10", "Priya Sen", "Goa plan final karte hain? 14 se 18 March. Jo aa rahe haan bolo")
    b("2025-03-01 20:12", ME, "main in 🙋")
    b("2025-03-01 20:13", "Rohan Das", media=vn("ek minute, Goa toh pakka hai bhai, main toh pehle se ready hoon, bas ghar pe bolna hai"))
    b("2025-03-01 20:15", "Abhishek Kundu", "in")
    b("2025-03-01 20:16", "Kabir Malhotra", "in in in")
    b("2025-03-01 20:18", "Arjun Mehta", "GOAAAA 🏖️🔥")
    b("2025-03-01 20:25", "Sayan Mukherjee", "Budget thoda tight hai this month, I'll skip this one. Next trip pakka.")
    b("2025-03-01 20:40", "Vikram Singh", "main bhi in shayad")
    b("2025-03-02 18:20", "Vikram Singh", "sorry guys main nahi aa paunga, ghar pe cousin ki shaadi hai 😞")
    b("2025-03-02 18:22", "Priya Sen", "aww Vikram 😞 next time pakka")
    b("2025-03-02 21:05", "Priya Sen", "tickets book ho gaye ✈️ 6 log: me, Suman, Rohan, Abhishek, Kabir, Arjun",
      img(header="IndiGo", lines=["6E-2134   CCU  →  GOI", "Fri, 14 Mar 2025   06:10", "PNR  K7XQ2M   ·   6 Adults", "Lead passenger: Priya Sen"], accent="#1a237e"))
    b("2025-03-10 22:00", "Sayan Mukherjee", "Packing list for the Goa people (please read):\n1. Aadhaar original\n2. Sunscreen\n3. Charger + power bank\n4. Tickets ka printout\nPoint being, last minute panic mat karna")
    b("2025-03-13 22:30", "Priya Sen", "kal 3:30 baje cab, 6:10 ki flight. Late hua toh chhod ke jayenge 😤")
    b("2025-03-14 04:12", "Abhishek Kundu", "BHAI TICKETS GHAR PE BHOOL GAYA 😭😭 printout wala")
    b("2025-03-14 04:13", "Priya Sen", "@\u2068Abhishek Kundu\u2069 PNR se ho jayega, chill. Aadhaar hai na?")
    b("2025-03-14 04:14", "Abhishek Kundu", "haan Aadhaar hai 😮‍💨")
    b("2025-03-14 04:16", "Rohan Das", media=vn("ek minute, Abhishek ne tickets bhool gaye, ye toh history mein likha jayega bhai"))
    b("2025-03-14 12:40", "Priya Sen", "location: https://maps.google.com/?q=15.5527,73.7517")
    b("2025-03-15 18:05", "Arjun Mehta", "Baga beach 🔥🔥", Media("video", {"frames": [("beach", "Baga Beach"), ("beach", "Goa trip day 2"), ("night", "shacks at night")]}))
    b("2025-03-15 18:07", "Kabir Malhotra", "", img(scene="beach", caption="Baga Beach, 15 Mar"))
    b("2025-03-15 18:10", ME, "best trip ever 🥹")
    b("2025-03-16 03:04", "Kabir Malhotra", "3 baje Maggi ban rahi hai, kaun kaun jaag raha hai? 🍜", img(scene="food", caption="Maggi, 3:04 AM"))
    b("2025-03-16 03:06", "Rohan Das", "main!! 3 baje Maggi best Maggi")
    b("2025-03-16 03:07", "Arjun Mehta", "3 baje Maggi squad 🔥")
    b("2025-03-18 22:15", "Priya Sen", "sab log 25 tak bhej dena please 🙏",
      img(header="Splitwise · Goa Trip 2025", lines=["Total spent      ₹84,600", "Per person       ₹14,100", "Paid by          Priya Sen", "Settle up by 25 Mar"], accent="#1cc29f"))
    b("2025-03-19 10:05", "Abhishek Kundu", "bhej diya ₹14,100 ✅")

    # April: farewell and the PPT joke
    b("2025-04-10 21:30", "Sayan Mukherjee", "Okay so for the seniors' farewell I have thought about three options. Option one is a restaurant in Park Street, around ₹800 per head, easy but boring. Option two is a terrace party at Kabir's place, cheaper but we need permission. Option three is a boat ride on the Ganga at sunset, honestly the most memorable. I think option three wins on experience per rupee.")
    b("2025-04-10 21:33", "Arjun Mehta", "bhai tu toh iska PPT bana de 😂😂")
    b("2025-04-10 21:34", "Rohan Das", "PPT bana de with animations 💀")
    b("2025-04-10 21:36", "Priya Sen", "boat ride final. Sayan coordinator 🫡")
    b("2025-04-26 19:20", "Priya Sen", "farewell done 🥹", img(scene="river", caption="Farewell boat ride, Ganga, 26 Apr"))

    # May: exams
    b("2025-05-02 18:00", "Priya Sen", "timetable aa gaya 😭",
      img(header="END SEMESTER EXAMINATION · MAY 2025", lines=["12 May   Database Management Systems", "15 May   Operating Systems", "19 May   Computer Networks", "22 May   Engineering Mathematics IV", "Reporting time 9:30 AM"], accent="#7b1f1f"))
    b("2025-05-11 01:48", "Kabir Malhotra", "kal DBMS hai aur maine normalization chhua bhi nahi 😭")
    b("2025-05-11 01:55", ME, "same bro. BCNF kya hota hai 💀")
    b("2025-05-14 23:10", "Priya Sen", "OS notes, unit 3 important hai", Media("document", {"title": "OS Unit 3 Notes", "file": "OS_Unit3_Notes.pdf",
      "lines": ["Process scheduling: FCFS, SJF, Round Robin", "Deadlock: mutual exclusion, hold and wait, no preemption, circular wait", "Banker's algorithm"]}))
    b("2025-05-15 15:20", "Ananya Roy", "OS paper ekdum bekar tha. mera toh gaya 😞")
    b("2025-05-15 15:22", "Ishita Banerjee", "mine too, round robin wala question samajh hi nahi aaya")
    b("2025-05-19 14:30", "Meera Iyer", "CN thoda theek tha at least")
    b("2025-05-22 13:05", "Priya Sen", "LAST EXAM DONE 🎉🎉 sab Coffee House aao 4 baje")
    b("2025-05-30 20:00", "Aditya Bose", "guys main kuch time ke liye off ho raha hoon, phone se break. take care 🙏")

    # July and August: the Darjeeling fight
    b("2025-07-08 13:10", "Meera Iyer", "Infosys internship mil gayi! 🎉")
    b("2025-07-08 13:12", "Priya Sen", "omg congrats Meera!!")
    b("2025-07-28 21:00", "Priya Sen", "Darjeeling chalein August mein? Independence day weekend")
    b("2025-08-03 20:00", "Priya Sen", "POLL:\nDarjeeling trip dates?\nOPTION: 14–17 Aug (6 votes)\nOPTION: 21–24 Aug (2 votes)")
    b("2025-08-04 19:30", "Sayan Mukherjee", "I've paid ₹6,000 advance for the homestay. Kabir, please send your share when you can.")
    b("2025-08-09 22:40", "Kabir Malhotra", "sorry guys, ghar pe emergency hai, trip cancel karna padega. maine booking cancel kar di",
      img(header="Mountain View Homestay, Darjeeling", lines=["Booking cancelled", "Refund ₹6,000 in 5–7 working days", "Cancelled by: Kabir Malhotra"], accent="#5a3e1b"))
    b("2025-08-09 22:45", "Sayan Mukherjee", "Kabir, I am saying this very calmly. You cancelled the booking without asking anyone, and the refund will only come back to my account after a week. Everyone had already taken leave. This is not about money, it is about telling people before deciding for the whole group.")
    b("2025-08-09 22:47", "Kabir Malhotra", "bhai tu har cheez ka hisaab rakhta hai, dosti mein bhi?")
    b("2025-08-09 22:48", "Sayan Mukherjee", "it is literally ₹2,400 of your share that I paid. You still owe me that.")
    b("2025-08-09 22:50", "Kabir Malhotra", "le le tera 2400, itna drama kyun")
    b("2025-08-09 22:51", "Priya Sen", "guys please, DM mein baat karo 🙏")
    b("2025-08-12 18:40", "Sayan Mukherjee", "",
      img(header="Splitwise · Darjeeling Trip", lines=["Kabir Malhotra owes Sayan Mukherjee", "₹2,400", "Unsettled"], accent="#1cc29f"))
    b("2025-08-12 18:45", "Kabir Malhotra", "seriously Sayan? group mein daal diya?")
    b("2025-08-14 16:20", None, "Kabir Malhotra left")
    b("2025-08-14 16:25", ME, "yaar ye sab kya ho gaya")
    b("2025-08-14 16:30", "Rohan Das", media=vn("ek minute, mujhe lagta hai sab thoda over react kar rahe hain, Kabir ko wapas add karo yaar"))
    b("2025-08-20 21:15", "Ishita Banerjee", "group itna quiet hai, sab theek ho?")

    # September: making up, Durga Puja
    b("2025-09-02 19:00", None, "Priya Sen added Kabir Malhotra")
    b("2025-09-02 19:02", "Kabir Malhotra", "sorry guys. Sayan bhai sorry yaar, galti meri thi. ₹2,400 bhej diya ✅")
    b("2025-09-02 19:05", "Sayan Mukherjee", "it's okay bro, I overreacted too. Chal ab 3 baje Maggi treat de 😂")
    b("2025-09-02 19:06", "Arjun Mehta", "3 baje Maggi reunion 🔥🔥")
    b("2025-09-02 19:07", "Priya Sen", "best news of the month 🥹")
    b("2025-09-02 19:09", "Rohan Das", media=vn("ek minute, finally sab theek ho gaya, ab Puja pe sab saath ghoomenge, koi drama nahi"))
    b("2025-09-15 22:00", "Sayan Mukherjee", "PPT bana diya finally 😂 route for Sashthi to Navami",
      Media("document", {"title": "Puja Pandal Route 2025", "file": "Puja_Pandal_Route_2025.pdf",
                         "lines": ["Sashthi: Santosh Mitra Square, College Square", "Saptami: Maddox Square adda", "Ashtami: anjali at Baghbazar", "Navami: Suruchi Sangha, Chetla Agrani"]}))
    b("2025-09-15 22:03", "Arjun Mehta", "PPT bana de wala banda ne actually PPT bana diya 💀")
    b("2025-09-21 22:30", "Priya Sen", "Mahalaya subah 4 baje, kaun uthega?")
    b("2025-09-28 21:10", "Priya Sen", "Sashthi 🥁", img(scene="pandal", caption="Santosh Mitra Square, Sashthi 2025"))
    b("2025-09-29 20:30", "Kabir Malhotra", "", img(scene="night", caption="Maddox Square adda, Saptami"))
    b("2025-10-01 21:30", "Arjun Mehta", "dhunuchi naach 🔥", Media("video", {"frames": [("pandal", "Navami night"), ("pandal", "dhunuchi naach"), ("night", "Maddox Square")]}))
    b("2025-10-02 18:00", "Ananya Roy", "Dashami 🥲 sindoor khela photos bhejo")
    b("2025-10-20 20:00", "Priya Sen", "Happy Diwali sab ko 🪔")

    # November to January: placements and plans
    b("2025-11-03 18:30", "Aditya Bose", "bhai main zinda hoon 😅 5 mahine baad. kya miss kiya maine?")
    b("2025-11-03 18:32", "Rohan Das", media=vn("ek minute ek minute, Aditya wapas aa gaya, bhai tune toh bahut kuch miss kiya, Goa ke baad sab kuch hua"))
    b("2025-11-03 18:33", "Arjun Mehta", "ADITYA IS BACK 🙌")
    b("2025-11-12 21:00", "Priya Sen", "placement drive kal se, sab resume update karo")
    b("2025-11-20 22:00", ME, "aptitude test cleared 😮‍💨 interview next week")
    b("2025-12-05 14:30", "Priya Sen", "PLACED 😭😭🎉",
      img(header="Offer Letter", lines=["Priya Sen", "TCS Digital  ·  ₹7.5 LPA", "Joining: July 2026"], accent="#0d47a1"))
    b("2025-12-06 11:00", ME, "mera bhi ho gaya!! Infosys 🎉")
    b("2025-12-06 11:03", "Arjun Mehta", "party kab hai dono ki 🥳")
    b("2025-12-24 20:45", "Kabir Malhotra", "Park Street lights 🎄 kaun aaya hai?", img(scene="night", caption="Park Street, 24 Dec"))
    b("2026-01-10 21:00", "Priya Sen", "farewell ki planning start karte hain. Ideas?")
    b("2026-01-10 21:02", "Sayan Mukherjee", "I can make a PPT 😂")
    b("2026-01-10 21:03", "Arjun Mehta", "PPT bana de 💀")
    b("2026-01-25 20:30", "Priya Sen", "Goa 2.0 reunion after placements? 🏖️")
    b("2026-01-25 20:32", "Abhishek Kundu", "is baar tickets main nahi bhoolunga 😂")
    return B


def active(name: str, ts: datetime) -> bool:
    if name == "Aditya Bose" and datetime(2025, 5, 31) <= ts < datetime(2025, 11, 3, 18, 31):
        return False
    if name == "Kabir Malhotra" and datetime(2025, 8, 14, 16, 20) <= ts < datetime(2025, 9, 2, 19, 0):
        return False
    return True


def day_factor(d: date) -> float:
    if date(2025, 3, 14) <= d <= date(2025, 3, 18):
        return 1.8
    if date(2025, 8, 15) <= d <= date(2025, 9, 1):
        return 0.25  # the silence after the fight
    if date(2025, 9, 27) <= d <= date(2025, 10, 2):
        return 1.8
    return 1.0


def filler_body(sender: str, ts: datetime, key) -> tuple[str, Media | None]:
    mood, _, topics = MONTHS[key]
    if sender == "Rohan Das" and rng.random() < 0.35:
        return "", vn(rng.choice(ROHAN_VN) if ts > JOKES["ek minute"][0] else rng.choice(ROHAN_VN[2:4] + ROHAN_VN[5:6] + ROHAN_VN[7:9]))
    if sender != "Rohan Das" and rng.random() < 0.015:
        return "", vn(rng.choice(OTHER_VN))
    if sender == "Arjun Mehta" and rng.random() < 0.10:
        options = [m for m in MEMES if m[2] is None or ts >= m[2]]
        top, bottom, _ = rng.choice(options)
        return "", Media("image", {"meme": (top, bottom)})
    if rng.random() < 0.03:
        return "", Media("sticker", {"label": rng.choice(["lol", "bruh", "yay", "sad", "ok", "omg"])})
    if rng.random() < 0.012:
        return "", img(scene=rng.choice(["city", "food", "night", "group"]), caption=rng.choice(["canteen adda", "Coffee House", "College Street", "after class", "Victoria"]))
    for phrase, (since, lines) in JOKES.items():
        if ts > since and rng.random() < 0.008:
            return rng.choice(lines), None
    if sender == "Sayan Mukherjee" and rng.random() < 0.18:
        return rng.choice(SAYAN_LONG), None
    r = rng.random()
    text = rng.choice(SHORT) if r < 0.35 else rng.choice(topics) if r < 0.6 else rng.choice(POOLS[mood])
    if sender == "Arjun Mehta" and rng.random() < 0.8:
        text += " " + "".join(rng.choice(EMOJI) for _ in range(rng.randint(1, 3)))
    return text, None


def group_filler() -> list[Msg]:
    out = []
    hours = list(range(24))
    hour_w = [3, 2, 1, 0.3, 0.1, 0.1, 0.2, 0.5, 1, 2, 2, 2, 3, 3, 2, 2, 3, 4, 5, 6, 7, 8, 8, 6]
    names = list(CAST)
    d = date(2025, 2, 4)
    while d <= date(2026, 1, 31):
        key = (d.year, d.month)
        lam = MONTHS[key][1] * day_factor(d) * 1.1
        sessions = sum(rng.random() < lam / 3 for _ in range(3)) + (rng.random() < max(0.0, lam - 1) / 2)
        for _ in range(sessions):
            start = datetime(d.year, d.month, d.day, rng.choices(hours, hour_w)[0], rng.randint(0, 59))
            avail = [n for n in names if active(n, start)]
            starter = rng.choices(avail, [CAST[n][1] for n in avail])[0]
            ts, speaker = start, starter
            for i in range(rng.randint(3, 12)):
                text, media = filler_body(speaker, ts, key)
                msg = Msg(ts, speaker, text, media)
                if media is None and rng.random() < 0.04 and i > 0:
                    other = rng.choice([n for n in avail if n != speaker and n != TANIA])
                    msg.text = f"@\u2068{other}\u2069 {msg.text}"
                msg.edited = media is None and rng.random() < 0.01
                msg.deleted = media is None and rng.random() < 0.006
                out.append(msg)
                ts += timedelta(seconds=rng.randint(15, 420))
                speaker = rng.choices(avail, [CAST[n][0] for n in avail])[0]
        if rng.random() < 0.07 and active("Kabir Malhotra", datetime(d.year, d.month, d.day)):  # Kabir, the night owl
            ts = datetime(d.year, d.month, d.day, rng.choice([0, 1, 2]), rng.randint(0, 59))
            for line in ["koi jaag raha hai?", "neend nahi aa rahi", "ye series khatam karke hi sounga"][: rng.randint(1, 3)]:
                out.append(Msg(ts, "Kabir Malhotra", line))
                ts += timedelta(minutes=rng.randint(1, 8))
        d += timedelta(days=1)
    return out


# ----------------------------------------------------------------------------- one-to-one
def shrimant_chat() -> list[Msg]:
    B = []

    def b(ts, sender, text="", media=None):
        B.append(Msg(t(ts), sender, text, media))

    b("2025-02-10 20:01", None, "Messages and calls are end-to-end encrypted. Only people in this chat can read, listen to, or share them.")
    b("2025-02-10 20:02", FRIEND, "bro kitne din baad! Sunday Victoria walk? like school days")
    b("2025-02-10 20:10", ME, "pakka. 10 baje gate pe")
    b("2025-02-16 10:40", FRIEND, "school ke baad pehli baar 🥹", img(scene="city", caption="Victoria Memorial, Sunday morning"))
    b("2025-06-12 00:00", ME, "Happy birthday bhai 🎂🎉 party kab?")
    b("2025-06-12 00:03", FRIEND, "thank you bro ❤️ Arsalan biryani on me")
    b("2025-07-03 21:04", ME, "bhai 2000 udhaar dega? month end pe lauta dunga, promise")
    b("2025-07-03 21:06", FRIEND, "haan bhej raha")
    b("2025-07-03 21:07", FRIEND, "", img(header="GPay · Payment successful", lines=["Paid to Suman Ghosh", "₹2,000", "3 Jul 2025, 9:07 PM", "UPI Ref 518429376011"], accent="#1a73e8"))
    b("2025-08-30 19:22", FRIEND, "mera 2000 😑 month end ho gaya")
    b("2025-08-30 19:30", ME, "next week pakka bhai 🙏")
    b("2025-10-15 21:00", FRIEND, "2000 kab? 😂 ab toh Puja bhi khatam")
    b("2025-11-09 18:00", FRIEND, "Mandarmani bike trip 22 Nov? hum 4 log: tu, main, Rajat, Tuhin")
    b("2025-11-09 18:05", ME, "in!! 🏍️")
    b("2025-11-20 22:10", ME, "bhai sorry, 22 ko mera placement test hai, Mandarmani skip karna padega 😞")
    b("2025-11-20 22:15", FRIEND, "kya yaar. theek hai, career first. next time pakka")
    b("2025-12-07 19:00", ME, "placement ho gaya bhai!! Infosys 🎉 tera 2000 + biryani treat")
    b("2025-12-07 19:02", FRIEND, media=vn("arre congrats bhai, bahut khushi hui, biryani Arsalan mein hi khayenge, aur haan 2000 bhi"))
    b("2025-12-08 12:30", ME, "", img(header="GPay · Payment successful", lines=["Paid to Shrimant", "₹2,000", "8 Dec 2025, 12:30 PM", "UPI Ref 534918027733"], accent="#1a73e8"))
    b("2025-12-08 12:31", FRIEND, "finally 😂😂 debt free")

    pool_f = ["kya kar raha hai?", "bro kal free hai?", "aaj match dekhega?", "Mohun Bagan jeet gaya 🔥", "tere college mein fest kab hai",
              "bhai bore ho raha hoon", "maa ne bola tujhe ghar bula", "tu kab aayega para mein", "chal phone kar", "biryani khayega? Arsalan?",
              "ye reel dekh 😂", "tera interview kaisa gaya", "chill kar, ho jayega", "good night bro"]
    pool_m = ["kuch nahi, assignment", "haan free hoon", "pakka", "ok bhai", "haha", "kal milte", "bas college", "thak gaya aaj",
              "Sunday pakka", "bhai sun", "lol", "acha", "theek hai", "haan bol"]
    d = date(2025, 2, 11)
    while d <= date(2026, 1, 31):
        if rng.random() < 0.28:
            ts = datetime(d.year, d.month, d.day, rng.choice([19, 20, 21, 22, 23]), rng.randint(0, 59))
            for i in range(rng.randint(2, 7)):
                sender = FRIEND if i % 2 == 0 else ME
                if sender == FRIEND and rng.random() < 0.05:
                    B.append(Msg(ts, sender, "", vn(rng.choice(["bhai sun, kal ka plan pakka rakh, main aa jaunga", "arre call kar na, bahut kuch batana hai"]))))
                else:
                    B.append(Msg(ts, sender, rng.choice(pool_f if sender == FRIEND else pool_m)))
                ts += timedelta(seconds=rng.randint(20, 600))
        d += timedelta(days=1)
    return B


# ----------------------------------------------------------------------------- rendering
def font(size: int, bold: bool = False):
    for name in (["arialbd.ttf"] if bold else []) + ["arial.ttf", "seguiemj.ttf", "DejaVuSans.ttf"]:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default(size)


SCENES = {  # (sky, ground, accent)
    "beach": ("#7ec8e3", "#f2d29b", "#1f8fb3"), "river": ("#f5b971", "#3d6e8a", "#e07b39"), "pandal": ("#2b0f3a", "#c0392b", "#f1c40f"),
    "night": ("#0b1026", "#2c2c3a", "#f9d342"), "food": ("#3b2a20", "#d9a441", "#f4e1b5"), "city": ("#b8d4e3", "#9e9e9e", "#f0e6d2"),
    "group": ("#e8d5b7", "#6b4f3a", "#c94f4f"),
}


def render_image(spec: dict) -> bytes:
    im = Image.new("RGB", (720, 540), "white")
    d = ImageDraw.Draw(im)
    if spec.get("meme"):
        top, bottom = spec["meme"]
        im.paste(rng.choice(["#3d405b", "#81b29a", "#e07a5f", "#264653"]), (0, 0, 720, 540))
        d.ellipse((260, 170, 460, 370), fill="#f2cc8f", outline="black", width=4)
        d.arc((310, 250, 410, 330), 20, 160, fill="black", width=5)
        for y, txt in ((30, top.upper()), (460, bottom.upper())):
            f = font(34, True)
            w = d.textlength(txt, font=f)
            d.text(((720 - w) / 2, y), txt, font=f, fill="white", stroke_width=3, stroke_fill="black")
    elif spec.get("scene"):
        sky, ground, accent = SCENES[spec["scene"]]
        d.rectangle((0, 0, 720, 300), fill=sky)
        d.rectangle((0, 300, 720, 540), fill=ground)
        for _ in range(6):
            x, y = rng.randint(20, 680), rng.randint(200, 420)
            d.ellipse((x, y, x + rng.randint(30, 90), y + rng.randint(30, 90)), fill=accent)
        d.rectangle((0, 470, 720, 540), fill="#111111")
        d.text((24, 488), spec.get("caption") or "", font=font(28, True), fill="white")
    else:
        d.rectangle((0, 0, 720, 96), fill=spec.get("accent") or "#333")
        d.text((32, 30), spec.get("header") or "", font=font(32, True), fill="white")
        for i, line in enumerate(spec.get("lines") or []):
            d.text((32, 140 + i * 64), line, font=font(30, i == 0), fill="#111111")
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=72)
    return buf.getvalue()


def render_sticker(spec: dict) -> bytes:
    im = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse((16, 16, 240, 240), fill=rng.choice(["#ffcc4d", "#c6f432", "#ff4f9c", "#7ec8e3"]), outline="black", width=6)
    f = font(48, True)
    w = d.textlength(spec["label"], font=f)
    d.text(((256 - w) / 2, 100), spec["label"], font=f, fill="black")
    buf = io.BytesIO()
    im.save(buf, "WEBP", quality=70)
    return buf.getvalue()


def render_pdf(spec: dict) -> bytes:
    lines = [spec["title"], ""] + spec["lines"]
    stream = "BT /F1 14 Tf 72 740 Td " + " ".join(f"({ln.encode('ascii', 'replace').decode()}) Tj 0 -22 Td" for ln in lines) + " ET"
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", "<< /Type /Pages /Kids [4 0 R] /Count 1 >>",
            "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 5 0 R /Resources << /Font << /F1 3 0 R >> >> >>",
            f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream"]
    out, offs = "%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += f"{i} 0 obj\n{o}\nendobj\n"
    x = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n" + "".join(f"{o:010d} 00000 n \n" for o in offs)
    return (out + f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{x}\n%%EOF").encode("latin-1")


def render_video(spec: dict, tmp: Path) -> bytes:
    for i, (scene, caption) in enumerate(spec["frames"]):
        Image.open(io.BytesIO(render_image({"scene": scene, "caption": caption}))).resize((640, 480)).save(tmp / f"f{i:02d}.png")
    out = tmp / "v.mp4"
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-framerate", "0.7", "-i", str(tmp / "f%02d.png"), "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", "-r", "24", str(out)], check=True)
    for f in tmp.glob("f*.png"):
        f.unlink()
    return out.read_bytes()


def render_voices(items: list[tuple[str, str, str]], tmp: Path) -> dict[str, bytes]:
    """[(key, text, gender)] -> {key: opus bytes}, via Windows speech, then ffmpeg to Opus like WhatsApp PTT."""
    jobs = [{"p": str(tmp / f"{k}.wav"), "t": text, "g": gender} for k, text, gender in items]
    (tmp / "jobs.json").write_text(json.dumps(jobs), encoding="utf-8")
    ps = (f"Add-Type -AssemblyName System.Speech; $s=New-Object System.Speech.Synthesis.SpeechSynthesizer; "
          f"foreach($j in (Get-Content -Raw -Encoding utf8 '{tmp / 'jobs.json'}' | ConvertFrom-Json)){{ "
          f"try {{ $s.SelectVoiceByHints($j.g) }} catch {{}}; $s.SetOutputToWaveFile($j.p); $s.Speak($j.t) }}; $s.Dispose()")
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True, capture_output=True)
    out = {}
    for k, _, _ in items:
        wav, opus = tmp / f"{k}.wav", tmp / f"{k}.opus"
        subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", str(wav), "-ac", "1", "-ar", "16000", "-c:a", "libopus",
                        "-b:a", "16k", "-f", "ogg", str(opus)], check=True)
        out[k] = opus.read_bytes()
    return out


# ----------------------------------------------------------------------------- export writers
EXT = {"image": "jpg", "voice": "opus", "video": "mp4", "sticker": "webp"}
ANDROID_PREFIX = {"image": "IMG", "voice": "PTT", "video": "VID", "sticker": "STK"}
IOS_TYPE = {"image": "PHOTO", "voice": "AUDIO", "video": "VIDEO", "sticker": "STICKER"}


def name_android(msgs: list[Msg]) -> None:
    per_day: dict[date, int] = {}
    for m in msgs:
        if m.media:
            n = per_day.get(m.ts.date(), 0)
            per_day[m.ts.date()] = n + 1
            k = m.media.kind
            m.media.name = m.media.spec["file"] if k == "document" else f"{ANDROID_PREFIX[k]}-{m.ts:%Y%m%d}-WA{n:04d}.{EXT[k]}"


def name_ios(msgs: list[Msg]) -> None:
    n = 0
    for m in msgs:
        if m.media:
            n += 1
            k = m.media.kind
            m.media.name = m.media.spec["file"] if k == "document" else f"{n:08d}-{IOS_TYPE[k]}-{m.ts:%Y-%m-%d-%H-%M-%S}.{EXT[k]}"


def android_line(m: Msg, with_media: bool) -> str:
    h = m.ts.hour % 12 or 12
    stamp = f"{m.ts:%d/%m/%y}, {h}:{m.ts:%M}\u202f{'am' if m.ts.hour < 12 else 'pm'}"
    if m.sender is None:
        return f"{stamp} - {m.text}"
    if m.deleted:
        body = "This message was deleted"
    elif m.media:
        body = (f"{m.media.name} (file attached)" + (f"\n{m.text}" if m.text else "")) if with_media else "<Media omitted>"
    else:
        body = m.text + (" <This message was edited>" if m.edited else "")
    return f"{stamp} - {m.sender}: {body}"


def ios_lines(m: Msg, system_sender: str) -> list[str]:
    h = m.ts.hour % 12 or 12
    stamp = f"[{m.ts:%d/%m/%y}, {h}:{m.ts:%M:%S}\u202f{'AM' if m.ts.hour < 12 else 'PM'}]"
    if m.sender is None:
        return [f"{stamp} {system_sender}: \u200e{m.text}"]
    if m.deleted:
        return [f"{stamp} {m.sender}: \u200eThis message was deleted."]
    if m.media:
        lines = [f"\u200e{stamp} {m.sender}: \u200e<attached: {m.media.name}>"]
        if m.text:
            later = m.ts + timedelta(seconds=1)
            lines.append(f"[{later:%d/%m/%y}, {later.hour % 12 or 12}:{later:%M:%S}\u202f{'AM' if later.hour < 12 else 'PM'}] {m.sender}: {m.text}")
        return lines
    return [f"{stamp} {m.sender}: {m.text}" + (" \u200e<This message was edited>" if m.edited else "")]


def render_all(msgs: list[Msg], prefix: str, tmp: Path) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    voices = []
    for i, m in enumerate(msgs):
        if not m.media:
            continue
        k, spec = m.media.kind, m.media.spec
        if k == "image":
            files[m.media.name] = render_image(spec)
        elif k == "sticker":
            files[m.media.name] = render_sticker(spec)
        elif k == "document":
            files[m.media.name] = render_pdf(spec)
        elif k == "video":
            files[m.media.name] = render_video(spec, tmp)
        elif k == "voice":
            voices.append((f"{prefix}{i}", spec["text"], CAST.get(m.sender, (0, 0, "Male"))[2], m.media.name))
    rendered = render_voices([(k, txt, g) for k, txt, g, _ in voices], tmp)
    for k, _, _, name in voices:
        files[name] = rendered[k]
    return files


def write_zip(path: Path, txt_name: str, text: str, files: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(txt_name, text)
        for name, data in files.items():
            z.writestr(name, data, compress_type=zipfile.ZIP_STORED)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "no-media").mkdir(exist_ok=True)
    group = sorted(group_beats() + group_filler(), key=lambda m: m.ts)
    direct = sorted(shrimant_chat(), key=lambda m: m.ts)
    name_android(group)
    name_ios(direct)
    for m in direct:  # iOS keeps seconds
        m.ts = m.ts.replace(second=rng.randint(0, 59))
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        print("rendering group media ...", flush=True)
        group_files = render_all(group, "g", tmp)
        print("rendering one-to-one media ...", flush=True)
        direct_files = render_all(direct, "d", tmp)

    group_txt = "\n".join(android_line(m, True) for m in group) + "\n"
    write_zip(OUT / f"WhatsApp Chat with {GROUP}.zip", f"WhatsApp Chat with {GROUP}.txt", group_txt, group_files)
    (OUT / "no-media" / f"WhatsApp Chat with {GROUP}.txt").write_text("\n".join(android_line(m, False) for m in group) + "\n", encoding="utf-8")
    direct_txt = "\n".join(line for m in direct for line in ios_lines(m, FRIEND)) + "\n"
    write_zip(OUT / f"WhatsApp Chat - {FRIEND}.zip", "_chat.txt", direct_txt, direct_files)

    facts = {
        "project": "Suman", "me": ME,
        "group": {"title": GROUP, "members": len(CAST), "driver": "Priya Sen", "voice_note_king": "Rohan Das",
                  "night_owl": "Kabir Malhotra", "ghost": "Aditya Bose", "lurker": "Dev Chatterjee", "essayist": "Sayan Mukherjee",
                  "hype_machine": "Arjun Mehta", "phone_number_member": TANIA,
                  "mood_low_months": ["2025-05", "2025-08"], "mood_high_months": ["2025-03", "2025-09"],
                  "fight": {"between": ["Kabir Malhotra", "Sayan Mukherjee"], "date": "2025-08-09", "amount": "₹2,400",
                            "left": "2025-08-14", "re_added": "2025-09-02"},
                  "goa": {"dates": "14-18 Mar 2025", "planned_on": "2025-03-01", "backed_out": "Vikram Singh",
                          "forgot_tickets": "Abhishek Kundu", "flight": "6E-2134", "total": "₹84,600"},
                  "inside_jokes": {"3 baje Maggi": {"started_by": "Kabir Malhotra", "first": "2025-03-16"},
                                   "ek minute": {"started_by": "Rohan Das", "first": "2025-02-03"},
                                   "PPT bana de": {"started_by": "Arjun Mehta", "first": "2025-04-10"}}},
        "direct": {"title": FRIEND, "loan": {"amount": "₹2,000", "lent": "2025-07-03", "repaid": "2025-12-08"},
                   "mandarmani": {"planned_on": "2025-11-09", "backed_out": ME, "reason": "placement test on 22 Nov"}},
        "counts": {"group_messages": len(group), "group_media": len(group_files), "direct_messages": len(direct), "direct_media": len(direct_files)},
    }
    (OUT / "facts.json").write_text(json.dumps(facts, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(facts["counts"]))


if __name__ == "__main__":
    sys.exit(main())
