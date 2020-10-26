import berlin_hp
import deflex
import my_reegis
from reegis import config as cfg
from oemof.tools import logger
import os


SCENARIOS = {
    "berlin_single_2014": "berlin_hp_2014_single.xls",
    "de21_2014": "deflex_2014_de21_csv",
    "de22_2014": "deflex_2014_de21_csv",
    "de21_without_berlin_2014": "deflex_2014_de21_without_berlin_csv",
}

SPLITTER = {
    "berlin": ["berlin_hp", "berlin_single"],
    "upstream": ["up_", "upstream"],
    "deflex": ["deflex"],
}

cfg.init(
    paths=[
        os.path.dirname(berlin_hp.__file__),
        os.path.dirname(deflex.__file__),
        os.path.dirname(my_reegis.__file__)
    ]
)


def init():
    # download files from a server
    # unpack and copy to p = cfg.get("paths", "phd")
    pass


def split_scenarios(sc):
    splitted = {}
    for g, kws in SPLITTER.items():
        splitted[g] = []
        for keyword in kws:
            for s in sc:
                if keyword in s.split(os.sep)[-1]:
                    splitted[g].append(s)
    return splitted


def reproduce_folder(path):
    sc = deflex.fetch_scenarios_from_dir(path=path, xls=True)
    sc = split_scenarios(sc)
    logf = os.path.join(path, "log.csv")
    # deflex.model_multi_scenarios(sc["deflex"], cpu_fraction=0.8, log_file=logf)
    # berlin_hp.model_scenarios(sc["berlin"])
    print(sc)
    my_reegis.model_multi_scenarios(sc["deflex"], sc["berlin"],
                                    cpu_fraction=0.8)


# def reproduce_scenario(name):
#     file = SCENARIOS[name]
#     p = cfg.get("paths", "phd")
#
#     if "berlin_hp" in file:
#         y = int([x for x in file.split("_") if x.isnumeric()][0])
#         bmain(year=y, path=p, file=file)
#     elif "deflex" in file:
#         fn_csv = os.path.join(p, file)
#         model_scenario(csv_path=fn_csv)


if __name__ == "__main__":
    logger.define_logging()
    reproduce_folder(cfg.get("paths", "phd"))
