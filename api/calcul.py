from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import math
import json
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "references.json")
with open(DATA_PATH, "r", encoding="utf-8") as f:
    REF_DATA = json.load(f)


class EchafaudageRequest(BaseModel):
    L: float
    H: float
    largeur: float
    protection_mur: str
    grutage: str
    stabilisation: str
    calage_type: str


@app.post("/api/calcul")
def calcul_echafaudage(req: EchafaudageRequest):

    L = req.L
    H = req.H
    largeur = req.largeur
    protection_mur = req.protection_mur.strip().upper() == "OUI"
    grutage = req.grutage.strip().upper() == "OUI"
    stabilisation = req.stabilisation.strip().lower()
    calage_type = req.calage_type.strip().lower()

    # 1) Travées & niveaux
    T = math.ceil(L / 2.5)
    N = math.ceil(H / 2.0)
    F = 1

    # 2) SOCLES / EMBASES / POTEAUX
    ALTASV5 = 2 * T + 2
    ALTKEMB = ALTASV5
    ALTKPT2 = ALTASV5
    ALTKPT4 = ALTASV5 * N

    # 3) LISSES DE LARGEUR 0,70 m / 1,00 m
    # Exemple T=1 / N=1 => 2 lisses de façade + 2 lisses d'extrémité = 4
    ALTKLC1 = (2 * T * N + 2 * N) if abs(largeur - 0.70) < 1e-6 else 0
    ALTKLC2 = (2 * T * N + 2 * N) if abs(largeur - 1.00) < 1e-6 else 0

    # 4) LISSES 2,50 m
    # Correction demandée :
    # même calcul que le garde-corps de chute avant soit OUI ou NON.
    # Exemple T=1 / H=2m / N=1 => 4
    # Exemple T=1 / H=4m / N=2 => 6
    ALTKLC5 = 2 * T + 2 * N

    # 5) PLANCHERS
    base_planchers = 2 * T * N
    corr_largeur = N if abs(largeur - 1.00) < 1e-6 else 0
    corr_mur = 2 if protection_mur else 0

    ALTKMC5 = base_planchers + corr_largeur - corr_mur

    # Correction largeur 1,00 m :
    # À partir de 2,00 m de haut, on ajoute les planchers acier
    # pour compléter à côté du plancher trappe.
    if H >= 2.0 and abs(largeur - 1.00) < 1e-6:
        ALTKMC5 += 2

    nb_trappes_par_facade = math.ceil(L / 20.0)

    # Pas de plancher trappe en dessous de 2,00 m
    if H >= 2.0:
        ALTKPE5 = F * N * nb_trappes_par_facade
    else:
        ALTKPE5 = 0

    # 6) DIAGONALES
    ALTKDV5 = 2 * F if protection_mur else 1 * F

    # 7) GARDE-CORPS
    ALTKGH5 = 2 * T * N if protection_mur else T * N
    ALTKGH1 = 2 * N if abs(largeur - 0.70) < 1e-6 else 0
    ALTKGH2 = 2 * N if abs(largeur - 1.00) < 1e-6 else 0

    # 8) PLINTHES
    ALTKPI5 = 2 * T * N

    # 9) STABILISATEURS
    ALT000675 = (T + 1) if (stabilisation == "stabilisateurs" and H <= 6.0) else 0

    # 10) CALAGE
    points_calage = ALTASV5 + ALT000675

    use_bois = calage_type in ("bois", "les_deux", "les deux")
    use_plastique = calage_type in ("plastique", "les_deux", "les deux")

    ALTAMX1 = points_calage if use_bois else 0
    ALTACPI = points_calage if use_plastique else 0

    # 11) AMARRAGE
    if stabilisation == "amarrage":
        POINTS_AMARRAGE = math.ceil((L * H) / 12.0)
    else:
        POINTS_AMARRAGE = 0

    ALTAA11 = POINTS_AMARRAGE
    ALTAPA2 = POINTS_AMARRAGE
    ALTL99P = POINTS_AMARRAGE

    # 12) GRUTAGE
    ALTRLEV = 4 if grutage else 0
    ALTKB12 = ALTKPT4 if grutage else 0
    ALTKB13 = ALTKEMB if grutage else 0
    ALTKFSV = ALTASV5 if grutage else 0

    quantites = {
        "ALTASV5": ALTASV5,
        "ALTKEMB": ALTKEMB,
        "ALTKPT2": ALTKPT2,
        "ALTKPT4": ALTKPT4,
        "ALTKLC1": ALTKLC1,
        "ALTKLC2": ALTKLC2,
        "ALTKLC5": ALTKLC5,
        "ALTKMC5": max(ALTKMC5, 0),
        "ALTKPE5": ALTKPE5,
        "ALTKDV5": ALTKDV5,
        "ALTKGH5": ALTKGH5,
        "ALTKGH1": ALTKGH1,
        "ALTKGH2": ALTKGH2,
        "ALTKPI5": ALTKPI5,
        "ALT000675": ALT000675,
        "ALTAMX1": ALTAMX1,
        "ALTACPI": ALTACPI,
        "ALTAA11": ALTAA11,
        "ALTAPA2": ALTAPA2,
        "ALTL99P": ALTL99P,
        "ALTRLEV": ALTRLEV,
        "ALTKB12": ALTKB12,
        "ALTKB13": ALTKB13,
        "ALTKFSV": ALTKFSV,
    }

    items = []
    poids_echafaudage = 0.0
    quantite_totale = 0

    for ref, qte in quantites.items():
        if qte <= 0:
            continue

        data = REF_DATA.get(ref, {})
        designation = data.get("designation", "")
        poids_unitaire = float(data.get("poids", 0) or 0)
        poids_total = poids_unitaire * qte

        poids_echafaudage += poids_total
        quantite_totale += qte

        items.append({
            "reference": ref,
            "designation": designation,
            "quantite": qte,
            "poids_unitaire": poids_unitaire,
            "poids_total": poids_total,
        })

    if quantite_totale == 0:
        poids_racks = 0.0
    elif quantite_totale < 10:
        poids_racks = 43.0
    elif quantite_totale <= 40:
        poids_racks = 173.0
    else:
        extra_sets = math.ceil((quantite_totale - 40) / 40.0)
        poids_racks = 173.0 + extra_sets * 130.0

    poids_total_global = poids_echafaudage + poids_racks

    SEUIL_NAVETTE = 350.0
    navette_autorisee = poids_total_global <= SEUIL_NAVETTE

    return {
        "items": items,
        "poids_echafaudage": poids_echafaudage,
        "poids_racks": poids_racks,
        "poids_total_global": poids_total_global,
        "seuil_navette": SEUIL_NAVETTE,
        "navette_autorisee": navette_autorisee,
        "meta": {
            "L": L,
            "H": H,
            "largeur": largeur,
            "T": T,
            "N": N,
            "protection_mur": protection_mur,
            "grutage": grutage,
            "stabilisation": stabilisation,
            "calage_type": calage_type,
            "quantite_totale": quantite_totale,
        },
    }
