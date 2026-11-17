"""
SkillPath AI — build_companies.py
Costruisce il dizionario aziende europee (reali + fittizie)
per la generazione delle work experience nei CV sintetici.

Uso (dalla radice del progetto):
    python src/build_companies.py --output ./dataset/supplementary
"""

import json
import argparse
from pathlib import Path


def build_companies() -> dict:

    # ── Aziende REALI per settore ISCO ───────────────────────────
    real_companies = [

        # ISCO 1 — Managers / Business
        {"id": "co_mckinsey",    "name": "McKinsey & Company",        "country": "USA",         "real": True,  "isco_sectors": ["1", "2"]},
        {"id": "co_bcg",         "name": "Boston Consulting Group",   "country": "USA",         "real": True,  "isco_sectors": ["1", "2"]},
        {"id": "co_pwc",         "name": "PricewaterhouseCoopers",    "country": "UK",          "real": True,  "isco_sectors": ["1", "2", "3"]},
        {"id": "co_deloitte",    "name": "Deloitte",                  "country": "UK",          "real": True,  "isco_sectors": ["1", "2", "3"]},
        {"id": "co_kpmg",        "name": "KPMG",                      "country": "Netherlands", "real": True,  "isco_sectors": ["1", "2"]},
        {"id": "co_ey",          "name": "Ernst & Young",             "country": "UK",          "real": True,  "isco_sectors": ["1", "2"]},
        {"id": "co_bain",        "name": "Bain & Company",            "country": "USA",         "real": True,  "isco_sectors": ["1", "2"]},
        {"id": "co_oliver",      "name": "Oliver Wyman",              "country": "USA",         "real": True,  "isco_sectors": ["1", "2"]},
        {"id": "co_reply",       "name": "Reply S.p.A.",              "country": "Italy",       "real": True,  "isco_sectors": ["1", "2", "3"]},
        {"id": "co_engineering", "name": "Engineering Ingegneria Informatica", "country": "Italy", "real": True, "isco_sectors": ["1", "2", "3"]},

        # ISCO 2 — Professionals / Tech
        {"id": "co_sap",         "name": "SAP SE",                    "country": "Germany",     "real": True,  "isco_sectors": ["2", "3"]},
        {"id": "co_siemens",     "name": "Siemens AG",                "country": "Germany",     "real": True,  "isco_sectors": ["2", "3", "7", "8"]},
        {"id": "co_philips",     "name": "Philips",                   "country": "Netherlands", "real": True,  "isco_sectors": ["2", "3"]},
        {"id": "co_ericsson",    "name": "Ericsson",                  "country": "Sweden",      "real": True,  "isco_sectors": ["2", "3"]},
        {"id": "co_nokia",       "name": "Nokia",                     "country": "Finland",     "real": True,  "isco_sectors": ["2", "3"]},
        {"id": "co_capgemini",   "name": "Capgemini",                 "country": "France",      "real": True,  "isco_sectors": ["2", "3"]},
        {"id": "co_accenture",   "name": "Accenture",                 "country": "Ireland",     "real": True,  "isco_sectors": ["2", "3"]},
        {"id": "co_ibm_eu",      "name": "IBM Europe",                "country": "France",      "real": True,  "isco_sectors": ["2", "3"]},
        {"id": "co_infosys",     "name": "Infosys BPM Europe",        "country": "Germany",     "real": True,  "isco_sectors": ["2", "3"]},
        {"id": "co_booking",     "name": "Booking.com",               "country": "Netherlands", "real": True,  "isco_sectors": ["2", "3"]},
        {"id": "co_spotify",     "name": "Spotify",                   "country": "Sweden",      "real": True,  "isco_sectors": ["2"]},
        {"id": "co_adyen",       "name": "Adyen",                     "country": "Netherlands", "real": True,  "isco_sectors": ["2", "3"]},

        # Telecom
        {"id": "co_tim",         "name": "TIM (Telecom Italia)",      "country": "Italy",       "real": True,  "isco_sectors": ["1", "2", "3", "4", "5"]},
        {"id": "co_wind",        "name": "Wind Tre S.p.A.",           "country": "Italy",       "real": True,  "isco_sectors": ["1", "2", "3", "4", "5"]},
        {"id": "co_vodafone_it", "name": "Vodafone Italia",           "country": "Italy",       "real": True,  "isco_sectors": ["1", "2", "3", "4", "5"]},
        {"id": "co_fastweb",     "name": "Fastweb S.p.A.",            "country": "Italy",       "real": True,  "isco_sectors": ["1", "2", "3", "4", "5"]},
        {"id": "co_vodafone_eu", "name": "Vodafone Group",            "country": "UK",          "real": True,  "isco_sectors": ["1", "2", "3", "4", "5"]},
        {"id": "co_orange",      "name": "Orange S.A.",               "country": "France",      "real": True,  "isco_sectors": ["1", "2", "3", "4", "5"]},
        {"id": "co_telekom",     "name": "Deutsche Telekom",          "country": "Germany",     "real": True,  "isco_sectors": ["1", "2", "3", "4", "5"]},
        {"id": "co_telefonica",  "name": "Telefónica",                "country": "Spain",       "real": True,  "isco_sectors": ["1", "2", "3", "4", "5"]},
        {"id": "co_swisscom",    "name": "Swisscom",                  "country": "Switzerland", "real": True,  "isco_sectors": ["1", "2", "3", "4"]},

        # ISCO 2 — Healthcare / Science
        {"id": "co_roche",       "name": "Roche",                     "country": "Switzerland", "real": True,  "isco_sectors": ["2", "3"]},
        {"id": "co_novartis",    "name": "Novartis",                  "country": "Switzerland", "real": True,  "isco_sectors": ["2", "3"]},
        {"id": "co_bayer",       "name": "Bayer AG",                  "country": "Germany",     "real": True,  "isco_sectors": ["2", "3", "6"]},
        {"id": "co_sanofi",      "name": "Sanofi",                    "country": "France",      "real": True,  "isco_sectors": ["2", "3"]},
        {"id": "co_astrazeneca", "name": "AstraZeneca",               "country": "UK",          "real": True,  "isco_sectors": ["2", "3"]},

        # ISCO 1/2 — Finance
        {"id": "co_bnpparibas",  "name": "BNP Paribas",               "country": "France",      "real": True,  "isco_sectors": ["1", "2", "3", "4"]},
        {"id": "co_unicredit",   "name": "UniCredit",                  "country": "Italy",       "real": True,  "isco_sectors": ["1", "2", "3", "4"]},
        {"id": "co_intesa",      "name": "Intesa Sanpaolo",            "country": "Italy",       "real": True,  "isco_sectors": ["1", "2", "3", "4"]},
        {"id": "co_ing",         "name": "ING Group",                  "country": "Netherlands", "real": True,  "isco_sectors": ["1", "2", "3", "4"]},
        {"id": "co_deutsche",    "name": "Deutsche Bank",              "country": "Germany",     "real": True,  "isco_sectors": ["1", "2", "3"]},
        {"id": "co_allianz",     "name": "Allianz SE",                 "country": "Germany",     "real": True,  "isco_sectors": ["1", "2", "3"]},

        # ISCO 5 — Retail / Hospitality
        {"id": "co_zara",        "name": "Zara (Inditex)",             "country": "Spain",       "real": True,  "isco_sectors": ["5", "4"]},
        {"id": "co_hm",          "name": "H&M",                        "country": "Sweden",      "real": True,  "isco_sectors": ["5", "4"]},
        {"id": "co_ikea",        "name": "IKEA",                       "country": "Sweden",      "real": True,  "isco_sectors": ["5", "4", "8"]},
        {"id": "co_carrefour",   "name": "Carrefour",                  "country": "France",      "real": True,  "isco_sectors": ["5", "4", "9"]},
        {"id": "co_lidl",        "name": "Lidl",                       "country": "Germany",     "real": True,  "isco_sectors": ["5", "4", "9"]},
        {"id": "co_hilton",      "name": "Hilton Hotels Europe",       "country": "UK",          "real": True,  "isco_sectors": ["5", "4"]},
        {"id": "co_accor",       "name": "Accor Hotels",               "country": "France",      "real": True,  "isco_sectors": ["5", "4"]},

        # ISCO 6 — Agriculture
        {"id": "co_basf",        "name": "BASF SE (Agro Division)",    "country": "Germany",     "real": True,  "isco_sectors": ["6", "2"]},
        {"id": "co_syngenta",    "name": "Syngenta",                   "country": "Switzerland", "real": True,  "isco_sectors": ["6", "2"]},

        # ISCO 7/8 — Manufacturing / Industrial
        {"id": "co_volkswagen",  "name": "Volkswagen AG",              "country": "Germany",     "real": True,  "isco_sectors": ["7", "8", "2", "3"]},
        {"id": "co_bmw",         "name": "BMW Group",                  "country": "Germany",     "real": True,  "isco_sectors": ["7", "8", "2", "3"]},
        {"id": "co_stellantis",  "name": "Stellantis",                 "country": "Netherlands", "real": True,  "isco_sectors": ["7", "8", "2", "3"]},
        {"id": "co_airbus",      "name": "Airbus",                     "country": "France",      "real": True,  "isco_sectors": ["7", "8", "2", "3"]},
        {"id": "co_bosch",       "name": "Robert Bosch GmbH",          "country": "Germany",     "real": True,  "isco_sectors": ["7", "8", "2", "3"]},
        {"id": "co_michelin",    "name": "Michelin",                   "country": "France",      "real": True,  "isco_sectors": ["7", "8"]},
        {"id": "co_saint_gobain","name": "Saint-Gobain",               "country": "France",      "real": True,  "isco_sectors": ["7", "8", "3"]},
        {"id": "co_electrolux",  "name": "Electrolux",                 "country": "Sweden",      "real": True,  "isco_sectors": ["7", "8"]},

        # Telecom
        {"id": "co_tim",         "name": "TIM (Telecom Italia)",       "country": "Italy",       "real": True,  "isco_sectors": ["1", "2", "3", "4", "5"]},
        {"id": "co_wind",        "name": "Wind Tre S.p.A.",            "country": "Italy",       "real": True,  "isco_sectors": ["1", "2", "3", "4", "5"]},
        {"id": "co_vodafone_it", "name": "Vodafone Italia",            "country": "Italy",       "real": True,  "isco_sectors": ["1", "2", "3", "4", "5"]},
        {"id": "co_fastweb",     "name": "Fastweb S.p.A.",             "country": "Italy",       "real": True,  "isco_sectors": ["1", "2", "3", "4", "5"]},
        {"id": "co_vodafone_eu", "name": "Vodafone Group",             "country": "UK",          "real": True,  "isco_sectors": ["1", "2", "3", "4", "5"]},
        {"id": "co_orange",      "name": "Orange S.A.",                "country": "France",      "real": True,  "isco_sectors": ["1", "2", "3", "4", "5"]},
        {"id": "co_telekom",     "name": "Deutsche Telekom",           "country": "Germany",     "real": True,  "isco_sectors": ["1", "2", "3", "4", "5"]},
        {"id": "co_telefonica",  "name": "Telefónica",                 "country": "Spain",       "real": True,  "isco_sectors": ["1", "2", "3", "4", "5"]},
        {"id": "co_swisscom",    "name": "Swisscom",                   "country": "Switzerland", "real": True,  "isco_sectors": ["1", "2", "3", "4"]},

        # Consulenza aggiuntiva
        {"id": "co_bain",        "name": "Bain & Company",             "country": "USA",         "real": True,  "isco_sectors": ["1", "2"]},
        {"id": "co_oliver",      "name": "Oliver Wyman",               "country": "USA",         "real": True,  "isco_sectors": ["1", "2"]},
        {"id": "co_reply",       "name": "Reply S.p.A.",               "country": "Italy",       "real": True,  "isco_sectors": ["1", "2", "3"]},
        {"id": "co_engineering", "name": "Engineering Ingegneria Informatica", "country": "Italy", "real": True, "isco_sectors": ["1", "2", "3"]},

        # Energia
        {"id": "co_enel",        "name": "Enel S.p.A.",                "country": "Italy",       "real": True,  "isco_sectors": ["1", "2", "3", "7", "8"]},
        {"id": "co_eni",         "name": "Eni S.p.A.",                 "country": "Italy",       "real": True,  "isco_sectors": ["1", "2", "3", "6", "7", "8"]},
        {"id": "co_total",       "name": "TotalEnergies",              "country": "France",      "real": True,  "isco_sectors": ["1", "2", "3", "6", "7", "8"]},
        {"id": "co_shell",       "name": "Shell",                      "country": "Netherlands", "real": True,  "isco_sectors": ["1", "2", "3", "6", "7", "8"]},
        {"id": "co_rwe",         "name": "RWE AG",                     "country": "Germany",     "real": True,  "isco_sectors": ["1", "2", "3", "7", "8"]},
        {"id": "co_edf",         "name": "EDF (Électricité de France)","country": "France",      "real": True,  "isco_sectors": ["1", "2", "3", "7", "8"]},
        {"id": "co_a2a",         "name": "A2A S.p.A.",                 "country": "Italy",       "real": True,  "isco_sectors": ["1", "2", "3", "7", "8"]},
        {"id": "co_snam",        "name": "Snam S.p.A.",                "country": "Italy",       "real": True,  "isco_sectors": ["1", "2", "3", "7", "8"]},

        # Logistica
        {"id": "co_dhl",         "name": "DHL Group",                  "country": "Germany",     "real": True,  "isco_sectors": ["1", "3", "4", "8", "9"]},
        {"id": "co_fedex",       "name": "FedEx Europe",               "country": "USA",         "real": True,  "isco_sectors": ["1", "3", "4", "8", "9"]},
        {"id": "co_ups",         "name": "UPS Europe",                 "country": "USA",         "real": True,  "isco_sectors": ["1", "3", "4", "8", "9"]},
        {"id": "co_gls",         "name": "GLS Group",                  "country": "Germany",     "real": True,  "isco_sectors": ["3", "4", "8", "9"]},
        {"id": "co_brt",         "name": "BRT Corriere Espresso",      "country": "Italy",       "real": True,  "isco_sectors": ["3", "4", "8", "9"]},
        {"id": "co_sda",         "name": "SDA Express Courier",        "country": "Italy",       "real": True,  "isco_sectors": ["3", "4", "8", "9"]},
        {"id": "co_maersk",      "name": "Maersk",                     "country": "Denmark",     "real": True,  "isco_sectors": ["1", "2", "3", "8", "9"]},
        {"id": "co_dbschenker",  "name": "DB Schenker",                "country": "Germany",     "real": True,  "isco_sectors": ["1", "3", "4", "8", "9"]},
        {"id": "co_kuehne",      "name": "Kuehne+Nagel",               "country": "Switzerland", "real": True,  "isco_sectors": ["1", "2", "3", "4", "8"]},

        # Retail / Fashion
        {"id": "co_gucci",       "name": "Gucci (Kering)",             "country": "Italy",       "real": True,  "isco_sectors": ["1", "2", "3", "5", "7"]},
        {"id": "co_ferragamo",   "name": "Salvatore Ferragamo",        "country": "Italy",       "real": True,  "isco_sectors": ["1", "2", "3", "5", "7"]},
        {"id": "co_luxottica",   "name": "Luxottica (EssilorLuxottica)","country": "Italy",      "real": True,  "isco_sectors": ["1", "2", "3", "5", "7", "8"]},
        {"id": "co_prada",       "name": "Prada Group",                "country": "Italy",       "real": True,  "isco_sectors": ["1", "2", "3", "5", "7"]},
        {"id": "co_lvmh",        "name": "LVMH",                       "country": "France",      "real": True,  "isco_sectors": ["1", "2", "3", "5", "7"]},
        {"id": "co_hermes",      "name": "Hermès",                     "country": "France",      "real": True,  "isco_sectors": ["1", "2", "5", "7"]},
        {"id": "co_zalando",     "name": "Zalando",                    "country": "Germany",     "real": True,  "isco_sectors": ["1", "2", "3", "4", "5"]},
        {"id": "co_primark",     "name": "Primark",                    "country": "Ireland",     "real": True,  "isco_sectors": ["5", "4", "9"]},
    ]

    # ── Aziende FITTIZIE per settore ISCO ─────────────────────────
    # Costruite con naming convention europea credibile
    fictional_companies = [

        # Tech / IT
        {"id": "co_f_nordtech",   "name": "NordTech Solutions AB",      "country": "Sweden",      "real": False, "isco_sectors": ["2", "3"]},
        {"id": "co_f_alphasoft",  "name": "AlphaSoft GmbH",             "country": "Germany",     "real": False, "isco_sectors": ["2", "3"]},
        {"id": "co_f_digitalia",  "name": "Digitalia S.r.l.",           "country": "Italy",       "real": False, "isco_sectors": ["2", "3"]},
        {"id": "co_f_pixelwave",  "name": "PixelWave B.V.",             "country": "Netherlands", "real": False, "isco_sectors": ["2", "3"]},
        {"id": "co_f_codeforge",  "name": "CodeForge S.A.S.",           "country": "France",      "real": False, "isco_sectors": ["2", "3"]},
        {"id": "co_f_cyberlink",  "name": "CyberLink Sp. z o.o.",       "country": "Poland",      "real": False, "isco_sectors": ["2", "3"]},
        {"id": "co_f_techvision", "name": "TechVision Kft.",            "country": "Hungary",     "real": False, "isco_sectors": ["2", "3"]},
        {"id": "co_f_databridge", "name": "DataBridge S.L.",            "country": "Spain",       "real": False, "isco_sectors": ["2", "3"]},

        # Finance / Consulting
        {"id": "co_f_eurofinance","name": "EuroFinance Advisors S.A.",  "country": "Belgium",     "real": False, "isco_sectors": ["1", "2", "3"]},
        {"id": "co_f_alphacons",  "name": "Alpha Consulting GmbH",      "country": "Austria",     "real": False, "isco_sectors": ["1", "2"]},
        {"id": "co_f_meridian",   "name": "Meridian Capital S.r.l.",    "country": "Italy",       "real": False, "isco_sectors": ["1", "2", "3"]},
        {"id": "co_f_nordbank",   "name": "NordBank A/S",               "country": "Denmark",     "real": False, "isco_sectors": ["1", "2", "3", "4"]},

        # Healthcare
        {"id": "co_f_vitacare",   "name": "VitaCare GmbH",              "country": "Germany",     "real": False, "isco_sectors": ["2", "3"]},
        {"id": "co_f_medplus",    "name": "MedPlus S.r.l.",             "country": "Italy",       "real": False, "isco_sectors": ["2", "3"]},
        {"id": "co_f_healthnet",  "name": "HealthNet B.V.",             "country": "Netherlands", "real": False, "isco_sectors": ["2", "3"]},

        # Education / Social
        {"id": "co_f_edugroup",   "name": "EduGroup S.A.",              "country": "France",      "real": False, "isco_sectors": ["2", "3", "4"]},
        {"id": "co_f_learnhub",   "name": "LearnHub Sp. z o.o.",        "country": "Poland",      "real": False, "isco_sectors": ["2", "3"]},

        # Retail / Hospitality
        {"id": "co_f_euromart",   "name": "EuroMart S.A.",              "country": "Spain",       "real": False, "isco_sectors": ["5", "4", "9"]},
        {"id": "co_f_bellaristor","name": "BellaRistoro S.r.l.",        "country": "Italy",       "real": False, "isco_sectors": ["5"]},
        {"id": "co_f_nordhotel",  "name": "NordHotel AB",               "country": "Sweden",      "real": False, "isco_sectors": ["5", "4"]},
        {"id": "co_f_secureplus", "name": "SecurePlus GmbH",            "country": "Germany",     "real": False, "isco_sectors": ["5", "3"]},

        # Agriculture / Food
        {"id": "co_f_greenfarm",  "name": "GreenFarm Cooperative",      "country": "Netherlands", "real": False, "isco_sectors": ["6"]},
        {"id": "co_f_agriplus",   "name": "AgriPlus S.r.l.",            "country": "Italy",       "real": False, "isco_sectors": ["6"]},
        {"id": "co_f_vineland",   "name": "Vineland Estate S.L.",       "country": "Spain",       "real": False, "isco_sectors": ["6"]},
        {"id": "co_f_bioprod",    "name": "BioProduits S.A.S.",         "country": "France",      "real": False, "isco_sectors": ["6", "2"]},

        # Manufacturing / Craft
        {"id": "co_f_metalwerk",  "name": "MetalWerk GmbH",             "country": "Germany",     "real": False, "isco_sectors": ["7", "8"]},
        {"id": "co_f_italicraft", "name": "ItaliCraft S.r.l.",          "country": "Italy",       "real": False, "isco_sectors": ["7"]},
        {"id": "co_f_nordmach",   "name": "NordMach A/S",               "country": "Denmark",     "real": False, "isco_sectors": ["7", "8"]},
        {"id": "co_f_poliind",    "name": "PoliIndustria S.A.",         "country": "Portugal",    "real": False, "isco_sectors": ["8", "7"]},
        {"id": "co_f_techassem",  "name": "TechAssembly B.V.",          "country": "Netherlands", "real": False, "isco_sectors": ["8", "3"]},

        # Logistics / Transport
        {"id": "co_f_eurofreight","name": "EuroFreight S.A.",           "country": "Belgium",     "real": False, "isco_sectors": ["8", "9", "4"]},
        {"id": "co_f_rapidlog",   "name": "RapidLog GmbH",              "country": "Germany",     "real": False, "isco_sectors": ["8", "9"]},
        {"id": "co_f_ibertrans",  "name": "IberTrans S.L.",             "country": "Spain",       "real": False, "isco_sectors": ["8", "9"]},

        # Clerical / Admin
        {"id": "co_f_eurobpo",    "name": "EuroBPO S.A.",               "country": "Luxembourg",  "real": False, "isco_sectors": ["4", "3"]},
        {"id": "co_f_adminpro",   "name": "AdminPro Sp. z o.o.",        "country": "Poland",      "real": False, "isco_sectors": ["4"]},

        # Elementary / Facility
        {"id": "co_f_cleanserv",  "name": "CleanServ S.r.l.",           "country": "Italy",       "real": False, "isco_sectors": ["9", "5"]},
        {"id": "co_f_facilityeu", "name": "FacilityEU B.V.",            "country": "Netherlands", "real": False, "isco_sectors": ["9", "5"]},
    ]

    all_companies = real_companies + fictional_companies

    # Indice per settore
    by_sector: dict = {}
    for c in all_companies:
        for sector in c["isco_sectors"]:
            by_sector.setdefault(sector, []).append(c["id"])

    return {
        "companies":  {c["id"]: c for c in all_companies},
        "by_sector":  by_sector,
        "stats": {
            "total":    len(all_companies),
            "real":     sum(1 for c in all_companies if c["real"]),
            "fictional":sum(1 for c in all_companies if not c["real"]),
        }
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="./dataset/supplementary")
    args = parser.parse_args()

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    data = build_companies()
    out_path = out_dir / "companies.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    size_kb = out_path.stat().st_size / 1024
    print(f"✓ companies.json ({size_kb:.0f} KB)")
    print(f"  Totale:    {data['stats']['total']} aziende")
    print(f"  Reali:     {data['stats']['real']}")
    print(f"  Fittizie:  {data['stats']['fictional']}")
    print(f"\n  Aziende per settore ISCO:")
    for sector in sorted(data["by_sector"].keys()):
        print(f"    ISCO {sector}: {len(data['by_sector'][sector])} aziende")


if __name__ == "__main__":
    main()
