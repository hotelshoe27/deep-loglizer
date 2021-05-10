"""
The interface to load log datasets. The datasets currently supported include
HDFS and BGL.

Authors:
    LogPAI Team

"""

import pandas as pd
import os
import numpy as np
import re
from sklearn.utils import shuffle
from collections import OrderedDict, defaultdict
from sklearn.model_selection import train_test_split
from torch.utils.data import Dataset


class log_dataset(Dataset):
    def __init__(self, session_dict, feature_type="semantics"):
        flatten_data_list = []
        # flatten all sessions
        for session_idx, data_dict in enumerate(session_dict.values()):
            features = data_dict["features"][feature_type]
            labels = data_dict["window_labels"]
            for window_idx in range(len(labels)):
                sample = {
                    "session_idx": session_idx,  # not session id
                    "features": features[window_idx],
                    "window_labels": labels[window_idx],
                    "session_labels": data_dict["label"],
                }
                flatten_data_list.append(sample)
        self.flatten_data_list = flatten_data_list

    def __len__(self):
        return len(self.flatten_data_list)

    def __getitem__(self, idx):
        return self.flatten_data_list[idx]


def load_HDFS(
    log_file,
    label_file,
    test_ratio=0.5,
    sequential_partition=True,
    random_seed=42,
):
    """Load HDFS structured log into train and test data

    Arguments
    ---------
        TODO

    Returns
    -------
        TODO
    """

    struct_log = pd.read_csv(log_file, engine="c", na_filter=False, memory_map=True)
    session_dict = OrderedDict()

    column_idx = {col: idx for idx, col in enumerate(struct_log.columns)}
    for row in struct_log.values:
        blkId_list = re.findall(r"(blk_-?\d+)", row[column_idx["Content"]])
        blkId_set = set(blkId_list)
        for blk_Id in blkId_set:
            if blk_Id not in session_dict:
                session_dict[blk_Id] = defaultdict(list)
            session_dict[blk_Id]["templates"].append(row[column_idx["EventTemplate"]])

    # assign labels
    label_data = pd.read_csv(label_file, engine="c", na_filter=False, memory_map=True)
    label_data_dict = dict(zip(label_data["BlockId"], label_data["Label"]))
    for k, v in session_dict.items():
        session_dict[k]["label"] = int(label_data_dict[k] == "Anomaly")

    # split data
    session_ids = list(session_dict.keys())
    session_labels = list(map(lambda x: label_data_dict[x], session_ids))
    (
        session_id_train,
        session_id_test,
        session_labels_train,
        session_labels_test,
    ) = train_test_split(
        session_ids,
        session_labels,
        test_size=test_ratio,
        shuffle=(sequential_partition == False),
        random_state=random_seed,
    )

    session_train = {k: session_dict[k] for k in session_id_train}
    session_test = {k: session_dict[k] for k in session_id_test}

    return session_train, session_test