import torch
import torch.nn.functional as F
from torch import nn
from deeploglizer.models import ForcastBasedModel
from IPython import embed


class AE(ForcastBasedModel):
    def __init__(
        self,
        meta_data,
        kernel_sizes=[2, 3, 4],
        hidden_size=100,
        embedding_dim=16,
        feature_type="sequentials",
        topk=5,
        use_tfidf=False,
        pretrain_matrix=None,
        freeze=False,
        device=-1,
    ):
        super().__init__(
            meta_data=meta_data,
            feature_type=feature_type,
            topk=topk,
            use_tfidf=use_tfidf,
            embedding_dim=embedding_dim,
            pretrain_matrix=pretrain_matrix,
            freeze=freeze,
            device=device,
        )
        num_labels = meta_data["num_labels"]
        self.feature_type = feature_type
        self.hidden_size = hidden_size
        self.use_tfidf = use_tfidf

        self.convs = nn.ModuleList(
            [nn.Conv2d(1, hidden_size, (K, embedding_dim)) for K in kernel_sizes]
        )

        self.criterion = nn.CrossEntropyLoss()
        self.prediction_layer = nn.Linear(
            self.hidden_size * len(kernel_sizes), num_labels
        )

    def forward(self, input_dict):
        y = input_dict["window_labels"].long().view(-1)
        self.batch_size = y.size()[0]
        x = input_dict["features"]
        x = self.embedder(x)

        if self.feature_type == "semantics":
            if not self.use_tfidf:
                x = x.sum(dim=-2)  # add tf-idf

        x = x.unsqueeze(1)

        x = [
            F.relu(conv(x)).squeeze(3) for conv in self.convs
        ]  # [(batch_size, hidden_size, seq_len), ...]*len(kernel_sizes)
        x = [
            F.max_pool1d(i, i.size(2)).squeeze(2) for i in x
        ]  # [(batch_size, hidden_size), ...] * len(kernel_sizes)
        representation = torch.cat(x, 1)
        logits = self.prediction_layer(representation)
        y_pred = logits.softmax(dim=-1)
        loss = self.criterion(logits, y)
        return_dict = {"loss": loss, "y_pred": y_pred}
        return return_dict