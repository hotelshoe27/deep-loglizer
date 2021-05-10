import torch
import pandas as pd
from collections import defaultdict
from deeploglizer.common.utils import set_device, tensor2flatten_arr
from sklearn.metrics import accuracy_score, f1_score, recall_score, precision_score
from torch import nn


class Embedder(nn.Module):
    def __init__(
        self,
        vocab_size,
        embedding_dim,
        pretrain_matrix=None,
        freeze=False,
        use_tfidf=False,
    ):
        super(Embedder, self).__init__()
        self.use_tfidf = use_tfidf
        if pretrain_matrix:
            self.embedding_layer = nn.Embedding.from_pretrained(
                weight, padding_idx=1, freeze=freeze
            )
        else:
            self.embedding_layer = nn.Embedding(
                vocab_size, embedding_dim, padding_idx=1
            )

    def forward(self, x):
        if self.use_tfidf:
            return torch.matmul(x, self.embedding_layer.weight.double())
        else:
            return self.embedding_layer(x)


class ForcastBasedModel(nn.Module):
    def __init__(
        self,
        meta_data,
        feature_type,
        topk,
        use_tfidf,
        embedding_dim,
        pretrain_matrix=None,
        freeze=False,
        device=-1,
    ):
        super(ForcastBasedModel, self).__init__()
        self.device = set_device(device)
        self.topk = topk
        self.meta_data = meta_data
        self.feature_type = feature_type

        if feature_type in ["semantics", "sequentials"]:
            self.embedder = Embedder(
                meta_data["vocab_size"],
                embedding_dim=embedding_dim,
                pretrain_matrix=meta_data.get("pretrain_matrix", None),
                freeze=freeze,
                use_tfidf=use_tfidf,
            )

    def evaluate(self, test_loader):
        self.eval()  # set to evaluation mode
        with torch.no_grad():
            y_pred = []
            store_dict = defaultdict(list)
            for batch_input in test_loader:
                return_dict = self.forward(self.__input2device(batch_input))
                y_pred = return_dict["y_pred"]
                y_pred_topk = torch.topk(y_pred, self.topk)[1]  # b x topk

                store_dict["session_idx"].extend(
                    tensor2flatten_arr(batch_input["session_idx"])
                )
                store_dict["session_labels"].extend(
                    tensor2flatten_arr(batch_input["session_labels"])
                )
                store_dict["window_labels"].extend(
                    tensor2flatten_arr(batch_input["window_labels"])
                )
                store_dict["y_pred_topk"].extend(y_pred_topk.data.cpu().numpy())

            store_df = pd.DataFrame(store_dict)
            store_df["window_anomaly"] = store_df.apply(
                lambda x: x["window_labels"] not in x["y_pred_topk"], axis=1
            ).astype(int)

            session_df = (
                store_df[["session_idx", "session_labels", "window_anomaly"]]
                .groupby("session_idx", as_index=False)
                .sum()
            )
            y = (session_df["session_labels"] > 0).astype(int)
            pred = (session_df["window_anomaly"] > 0).astype(int)
            window_topk_acc = 1 - store_df["window_anomaly"].sum() / len(store_df)
            eval_results = {
                "f1": f1_score(y, pred),
                "rc": recall_score(y, pred),
                "pc": precision_score(y, pred),
                "top{}-acc".format(self.topk): window_topk_acc,
            }
            return eval_results

    def __input2device(self, batch_input):
        return {k: v.to(self.device) for k, v in batch_input.items()}

    def fit(self, train_loader, epoches=10, learning_rate=1.0e-3):
        self.to(self.device)
        print(
            "Start training on {} batches with {}.".format(
                len(train_loader), self.device
            )
        )
        for epoch in range(epoches):
            model = self.train()
            optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate)

            batch_cnt = 0
            epoch_loss = 0
            for batch_input in train_loader:
                loss = model.forward(self.__input2device(batch_input))["loss"]
                loss.backward()
                optimizer.step()
                optimizer.zero_grad()
                epoch_loss += loss.item()
                batch_cnt += 1
            epoch_loss = epoch_loss / batch_cnt
            print(
                "Epoch {}/{}, training loss: {:.5f}".format(
                    epoch + 1, epoches, epoch_loss
                )
            )