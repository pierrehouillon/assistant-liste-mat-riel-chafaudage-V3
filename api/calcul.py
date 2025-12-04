from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import math
import json
import os

app = FastAPI()

# CORS : autoriser l'appli web (Glide / Vercel) à appeler l'API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tu pourras restreindre à ton domaine Glide si besoin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Chargement des références (désignation + poids unitaire)
DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "references.json")
with open(DATA_PATH, "r", encoding="utf-8") as f:
    REF_DATA = json.load(f)


class EchafaudageRequest(BaseModel):
    L: float              # longueur façade (m)
    H: float              # hauteur du dernier niveau (m)
    largeur: float        # 0.7 ou 1.0
    protection_mur: str   # "OUI" / "NON"
    grutage: str          # "OUI" / "NON"
    stabilisation: str    # "stabilisateurs" / "amarrage"
    calage_type: str      # "bois" / "plastique" / "les_deux"


@app.post("/api/calcul")
def calcul_echafaudage(req: EchafaudageRequest):
    """
    Calcule les quantités d'éléments ALTRAD METRIX, ainsi que :
    - le poids total échafaudage
    - le poids estimé des racks / paniers
    - le poids total global
    """

    L = req.L
    H = req.H
    largeur = req.largeur
    protection_mur = req.protection_mur.strip().upper() == "OUI"
    grutage = req.grutage.strip().upper() == "OUI"
    stabilisation = req.stabilisation.strip().lower()  # "stabilisateurs" ou "amarrage"
    calage_type = req.calage_type.strip().lower()      # "bois" / "plastique" / "les_deux"

    # 1) Travées & niveaux
    T = math.ceil(L / 2.5)   # travées
    N = math.ceil(H / 2.0)   # niveaux
    F = 1                    # on considère 1 façade

    # 2) SOCLES / EMBASES / POTEAUX
    ALTASV5 = 2 * T + 2
    ALTKEMB = ALTASV5
    ALTKPT2 = ALTASV5
    ALTKPT4 = ALTASV5 * N

    # 3) LISSES
    ALTKLC1 = 2 * T * N if abs(largeur - 0.70) < 1e-6 else 0
    ALTKLC2 = 2 * T * N if abs(largeur - 1.00) < 1e-6 else 0
    if protection_mur:
        ALTKLC5 = 2 * T + 2 * N
    else:
        ALTKLC5 = 2 * T + N

    # 4) PLANCHERS
    base_planchers = 2 * T * N
    corr_largeur = N if abs(largeur - 1.00) < 1e-6 else 0
    corr_mur = 2 if protection_mur else 0
    ALTKMC5 = base_planchers + corr_largeur - corr_mur

    nb_trappes_par_facade = math.ceil(L / 20.0)
    ALTKPE5 = F * N * nb_trappes_par_facade

    # 5) DIAGONALES
    ALTKDV5 = 2 * F if protection_mur else 1 * F

    # 6) GARDE-CORPS
    ALTKGH5 = 2 * T * N if protection_mur else T * N
    ALTKGH1 = 2 * N if abs(largeur - 0.70) < 1e-6 else 0
    ALTKGH2 = 2 * N if abs(largeur - 1.00) < 1e-6 else 0

    # 7) PLINTHES
    ALTKPI5 = 2 * T * N

    # 8) STABILISATEURS
    ALT000675 = (T + 1) if (stabilisation == "stabilisateurs" and H <= 6.0) else 0

    # 9) CALAGE (en fonction du choix utilisateur)
    # nombre de points de calage = 1 par socle + 1 par stabilisateur télescopique
    points_calage = ALTASV5 + ALT000675

    use_bois = calage_type in ("bois", "les_deux", "les deux")
    use_plastique = calage_type in ("plastique", "les_deux", "les deux")

    ALTAMX1 = points_calage if use_bois else 0
    ALTACPI = points_calage if use_plastique else 0

    # 10) AMARRAGE
    if stabilisation == "amarrage":
        POINTS_AMARRAGE = math.ceil((L * H) / 12.0)
    else:
        POINTS_AMARRAGE = 0
    ALTAA11 = POINTS_AMARRAGE
    ALTAPA2 = POINTS_AMARRAGE
    ALTL99P = POINTS_AMARRAGE

    # 11) GRUTAGE
    ALTRLEV = 4 if grutage else 0
    ALTKB12 = ALTKPT4 if grutage else 0
    ALTKB13 = ALTKEMB if grutage else 0
    ALTKFSV = ALTASV5 if grutage else 0

    # 12) Quantités
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

    # 13) Lignes + poids échafaudage + quantité totale de pièces
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

        items.append(
            {
                "reference": ref,
                "designation": designation,
                "quantite": qte,
                "poids_unitaire": poids_unitaire,
                "poids_total": poids_total,
            }
        )

    # 14) Poids racks / paniers basé sur la QUANTITÉ TOTALE DE PIÈCES
    #   - < 10 pièces : 1 châssis seul (~43 kg)
    #   - 10 à 40 pièces : 1 châssis + 1 panier (~173 kg)
    #   - > 40 pièces : 1 châssis + 1 panier + 1 panier supplémentaire par tranche de 40 pièces au-delà de 40
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
