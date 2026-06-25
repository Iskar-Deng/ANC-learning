import os
from pathlib import Path
from typing import Any, Dict, Tuple


JsonDict = Dict[str, Any]


PROJECT_ROOT = Path(__file__).resolve().parent

ACE_BIN = os.environ.get(
    "ACE_BIN",
    str(PROJECT_ROOT / "bin" / "ace-0.9.34" / "ace"),
)

MRS_REWRITE_RULES = [
    ("SF: prop-or-ques", "SF: iforce"),
    ("COG-ST: uniq-id", "COG-ST: cog-st"),
    ("COG-ST: in-foc", "COG-ST: cog-st"),
]

CLAUSE_WOS = ["sov", "svo", "vos"]
NP_WOS = ["gn", "ng"]

ALIGNMENT_CODES = {
    "ac": "nom-acc",
    "er": "erg-abs",
}

COMP_SYSTEM_CODES = {
    "b": "balancing",
    "d": "deranking",
}

STRATEGY_CODES = {
    "se": "sent",
    "pa": "poss-acc",
    "ep": "erg-poss",
    "no": "nomn",
}


ANC_WO_CHOICE_TABLE = {
    ("sov", "gn"): {
        "sent": "sov",
        "poss-acc": "sov",
        "erg-poss": "sov",
        "nomn": "sov",
    },
    ("svo", "gn"): {
        "sent": "svo",
        "poss-acc": "svo",
        "erg-poss": "sov",
        "nomn": "svo",
    },
    ("vos", "gn"): {
        "sent": "vos",
        "poss-acc": "svo",
        "erg-poss": "sov",
        "nomn": "svo",
    },
    ("sov", "ng"): {
        "sent": "sov",
        "poss-acc": "ovs",
        "erg-poss": "vos",
        "nomn": "ovs",
    },
    ("svo", "ng"): {
        "sent": "svo",
        "poss-acc": "vos",
        "erg-poss": "vos",
        "nomn": "vos",
    },
    ("vos", "ng"): {
        "sent": "vos",
        "poss-acc": "vos",
        "erg-poss": "vos",
        "nomn": "vos",
    },
}


ANC_IV_ORDER_TABLE = {
    ("sov", "gn"): {
        "sent": "SV",
        "poss-acc": "SV",
        "erg-poss": "SV",
        "nomn": "SV",
    },
    ("svo", "gn"): {
        "sent": "SV",
        "poss-acc": "SV",
        "erg-poss": "SV",
        "nomn": "SV",
    },
    ("vos", "gn"): {
        "sent": "VS",
        "poss-acc": "SV",
        "erg-poss": "SV",
        "nomn": "SV",
    },
    ("sov", "ng"): {
        "sent": "SV",
        "poss-acc": "VS",
        "erg-poss": "VS",
        "nomn": "VS",
    },
    ("svo", "ng"): {
        "sent": "SV",
        "poss-acc": "VS",
        "erg-poss": "VS",
        "nomn": "VS",
    },
    ("vos", "ng"): {
        "sent": "VS",
        "poss-acc": "VS",
        "erg-poss": "VS",
        "nomn": "VS",
    },
}


ANC_TV_ORDER_TABLE = {
    ("sov", "gn"): {
        "sent": "APV",
        "poss-acc": "APV",
        "erg-poss": "APV",
        "nomn": "APV",
    },
    ("svo", "gn"): {
        "sent": "AVP",
        "poss-acc": "AVP",
        "erg-poss": "PVA",
        "nomn": "AVP",
    },
    ("vos", "gn"): {
        "sent": "VPA",
        "poss-acc": "AVP",
        "erg-poss": "PVA",
        "nomn": "AVP",
    },
    ("sov", "ng"): {
        "sent": "APV",
        "poss-acc": "PVA",
        "erg-poss": "AVP",
        "nomn": "PVA",
    },
    ("svo", "ng"): {
        "sent": "AVP",
        "poss-acc": "VPA",
        "erg-poss": "VPA",
        "nomn": "VPA",
    },
    ("vos", "ng"): {
        "sent": "VPA",
        "poss-acc": "VPA",
        "erg-poss": "VPA",
        "nomn": "VPA",
    },
}


def parse_language_id(language: str) -> JsonDict:
    parts = language.split("_")
    if len(parts) != 6:
        raise ValueError(
            f"Invalid language id: {language}. "
            "Expected format: <id>_<clause_wo>_<np_wo>_<alignment>_<comp>_<strategy>"
        )

    numeric_id, clause_wo, np_wo, alignment_code, comp_code, strategy_code = parts

    if clause_wo not in CLAUSE_WOS:
        raise ValueError(f"Invalid clause word order in language id: {clause_wo}")
    if np_wo not in NP_WOS:
        raise ValueError(f"Invalid NP word order in language id: {np_wo}")
    if alignment_code not in ALIGNMENT_CODES:
        raise ValueError(f"Invalid alignment code in language id: {alignment_code}")
    if comp_code not in COMP_SYSTEM_CODES:
        raise ValueError(f"Invalid complement-system code in language id: {comp_code}")
    if strategy_code not in STRATEGY_CODES:
        raise ValueError(f"Invalid ANC strategy code in language id: {strategy_code}")

    alignment = ALIGNMENT_CODES[alignment_code]
    comp_system = COMP_SYSTEM_CODES[comp_code]
    strategy = STRATEGY_CODES[strategy_code]
    key = (clause_wo, np_wo)
    anc_wo_choice = ANC_WO_CHOICE_TABLE[key][strategy]

    return {
        "id": numeric_id,
        "language": language,
        "clause_wo": clause_wo,
        "np_wo": np_wo,
        "alignment_code": alignment_code,
        "alignment": alignment,
        "comp_system_code": comp_code,
        "comp_system": comp_system,
        "strategy_code": strategy_code,
        "strategy": strategy,
        "anc_wo": anc_wo_choice,
        "anc_wo_choice": anc_wo_choice,
        "anc_iv_order": ANC_IV_ORDER_TABLE[key][strategy],
        "anc_tv_order": ANC_TV_ORDER_TABLE[key][strategy],
    }


def derive_fin_marks(alignment: str) -> Dict[str, str]:
    if alignment == "nom-acc":
        return {
            "FIN_S_MARK": "",
            "FIN_A_MARK": "",
            "FIN_P_MARK": "ca",
        }
    if alignment == "erg-abs":
        return {
            "FIN_S_MARK": "",
            "FIN_A_MARK": "ca",
            "FIN_P_MARK": "",
        }
    raise ValueError(alignment)


def derive_anc_marks(strategy: str, fin_marks: Dict[str, str]) -> Dict[str, str]:
    if strategy == "sent":
        return {
            "ANC_S_MARK": fin_marks["FIN_S_MARK"],
            "ANC_A_MARK": fin_marks["FIN_A_MARK"],
            "ANC_P_MARK": fin_marks["FIN_P_MARK"],
        }
    if strategy == "poss-acc":
        return {
            "ANC_S_MARK": "ge",
            "ANC_A_MARK": "ge",
            "ANC_P_MARK": fin_marks["FIN_P_MARK"],
        }
    if strategy == "erg-poss":
        return {
            "ANC_S_MARK": "ge",
            "ANC_A_MARK": "ob",
            "ANC_P_MARK": "ge",
        }
    if strategy == "nomn":
        return {
            "ANC_S_MARK": "ge",
            "ANC_A_MARK": "ge",
            "ANC_P_MARK": "ob",
        }
    raise ValueError(strategy)


def derive_language_config(language: str) -> JsonDict:
    params = parse_language_id(language)
    fin_marks = derive_fin_marks(params["alignment"])
    anc_marks = derive_anc_marks(params["strategy"], fin_marks)
    return {
        **params,
        **fin_marks,
        **anc_marks,
    }


def expected_ap_order(anc_tv_order: str) -> Tuple[str, str]:
    order = anc_tv_order.lower()

    if "a" in order and "p" in order:
        return ("A", "P") if order.index("a") < order.index("p") else ("P", "A")

    if "s" in order and "o" in order:
        return ("A", "P") if order.index("s") < order.index("o") else ("P", "A")

    raise ValueError(f"Invalid ANC transitive word order: {anc_tv_order}")

TRAINING_CONFIG = {
    # model / tokenizer
    "model_name": "gpt2",
    "text_field": "sent",

    # data
    "block_size": 32,

    # training
    "seed": 42,
    "max_steps": 70000,
    "per_device_train_batch_size": 16,
    "per_device_eval_batch_size": 16,
    "gradient_accumulation_steps": 2,
    "learning_rate": 5e-4,
    "warmup_steps": 590,
    "weight_decay": 0.01,

    # logging / saving
    "logging_steps": 100,
    "eval_steps": 5000,
    "save_steps": 5000,
    "save_total_limit": 1,

    # dataloader
    "dataloader_num_workers": 0,
}
