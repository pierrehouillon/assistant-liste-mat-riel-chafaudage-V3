from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import math
import json
import os

app = FastAPI()

# Autoriser frontend Vercel + Glide
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Charger données
DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "references.json")
with open(DATA_PATH, "r", encoding="utf-8") as f:
    REF_DATA = json.load(f)


class EchafaudageRequest(BaseModel):
    L: float
    H: float
    largeur: float
    F: int
    protection_mur: str
    grutage: str
    stabilisation: str


@app.post("/calcul")
def calcul(req: EchafaudageRequest):
    L = req.L
    H = req.H
    F = req.F
    largeur = req.largeur
    protection_mur = req.protection_mur == "OUI"
    grutage = req.grutage == "OUI"
    stabilisation = req.stabilisation

    # Travées & hauteurs
    T = math.ceil(L / 2.5)
    N = math.ceil(H / 2)

    # Quantités ALTRAD
    ALTASV5 = 2 * T + 2
    ALTKEMB12 = ALTASV5
    ALTKPT2 = ALTASV5
    ALTKPT4 = ALTASV5 * N

    ALTKLC1 = 2 * T * N if largeur == 0.70 else 0
    ALTKLC2 = 2 * T * N if largeur == 1.00 else 0
    ALTKLC5 = (2*T + 2*N) if protection_mur else (2*T + N)

    base = 2 * T * N
    corr = N if largeur == 1.00 else 0
    ALTKMC5 = base + corr - (2 if protection_mur else 0)

    ALTKPE5 = F * N
    ALTKDV5 = 2*F if protection_mur else F

    ALTKGH5 = 2*T*N if protection_mur else T*N
    ALTKGH1 = 2*N if largeur == 0.70 else 0
    ALTKGH2 = 2*N if largeur == 1.00 else 0

    ALTKPI5 = 2*T*N

    ALT000675 = (T + 1) if (stabilisation == "stabilisateurs" and H <= 6) else 0

    POINTS = math.ceil((L * H) / 12) if stabilisation == "amarrage" else 0
    ALTAA11 = POINTS
    ALTAPA2 = POINTS
    ALTL99P = POINTS

    ALTRLEV = 4 if grutage else 0
    ALTKB12 = ALTKPT4 if grutage else 0
    ALTKB13 = ALTKEMB12 if grutage else 0
    ALTKFSV = ALTASV5 if grutage else 0

    quantites = {
        "ALTASV5": ALTASV5,
        "ALTKEMB12": ALTKEMB12,
        "ALTKPT2": ALTKPT2,
        "ALTKPT4": ALTKPT4,
        "ALTKLC1": ALTKLC1,
        "ALTKLC2": ALTKLC2,
        "ALTKLC5": ALTKLC5,
        "ALTKMC5": ALTKMC5,
        "ALTKPE5": ALTKPE5,
        "ALTKDV5": ALTKDV5,
        "ALTKGH5": ALTKGH5,
        "ALTKGH1": ALTKGH1,
        "ALTKGH2": ALTKGH2,
        "ALTKPI5": ALTKPI5,
        "ALT000675": ALT000675,
        "ALTAA11": ALTAA11,
        "ALTAPA2": ALTAPA2,
        "ALTL99P": ALTL99P,
        "ALTRLEV": ALTRLEV,
        "ALTKB12": ALTKB12,
        "ALTKB13": ALTKB13,
        "ALTKFSV": ALTKFSV
    }

    rows = []
    for ref, qte in quantites.items():
        if qte > 0:
            rows.append({
                "reference": ref,
                "designation": REF_DATA.get(ref, ""),
                "quantite": qte
            })

    return {"items": rows}
