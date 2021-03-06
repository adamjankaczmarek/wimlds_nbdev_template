# AUTOGENERATED! DO NOT EDIT! File to edit: bert_experiments/00_bert_token_classifier.ipynb (unless otherwise specified).

__all__ = ['BertTokenClassifier']

# Cell

import os
import yaml
import argparse
import torch
import joblib
import lineflow as lf
from torch.utils.data import DataLoader, SequentialSampler, RandomSampler
import pytorch_lightning as pl
from pytorch_lightning.callbacks import EarlyStopping, ModelCheckpoint
from pytorch_lightning.loggers import TensorBoardLogger
from transformers import BertForTokenClassification, BertTokenizer, AdamW
from transformers import get_linear_schedule_with_warmup
from tqdm import tqdm

class BertTokenClassifier(pl.LightningModule):
    """
    BertTokenClassifier module for training Bert models for Token Classification Problem
    eg. Named Entity Recognition
    """

    def __init__(self, config):
        super(BertTokenClassifier, self).__init__()
        self.config = config
        self.tokenizer = BertTokenizer.from_pretrained(self.config["model"]["bert"], do_lower_case=config["data"]["lower_case"])
        self.model = BertForTokenClassification.from_pretrained(self.config["model"]["bert"], num_labels=2, output_attentions=False, output_hidden_states=False)

    # Execute

    def forward(batch):
        return self.model(**batch)

    # Optimizers

    def configure_optimizers(self):
        optimizer = AdamW(self.model.parameters(), lr=float(self.config["model"]['lr']))
        #total_steps =  * config["model"]["epochs"]
        #scheduler = get_linear_schedule_with_warmup(optimizer, num_warmup_steps=0, num_training_steps=total_steps)
        #return [optimizer], [scheduler]
        return optimizer

    # Train/Validate/Test

    def training_step(self, batch, batch_idx):
        loss, _ = self.model(**batch)
        tqdm_dict = {"train_loss": loss}
        output = {"loss": loss, "progress_bar": tqdm_dict,"log": tqdm_dict}
        return output

    def validation_step(self, batch, batch_idx):
        loss, logits = self.model(**batch)
        labels_hat = torch.argmax(logits, dim=-1)
        correct_count = torch.sum((batch['labels'] == labels_hat) * batch['attention_mask'])

        if self.on_gpu:
            correct_count = correct_count.cuda(loss.device.index)

        return {"val_loss": loss, "correct_count": correct_count, "batch_size": len(batch['labels']), "total_labels": batch['attention_mask'].sum()}

    def validation_end(self, outputs):
        val_acc = sum([out["correct_count"] for out in outputs]).float() / sum(out["total_labels"] for out in outputs)
        val_loss = sum([out["val_loss"] for out in outputs]) / len(outputs)
        tqdm_dict = {"val_loss": val_loss, "val_acc": val_acc}
        return {"progress_bar": tqdm_dict, "log": tqdm_dict, "val_loss": val_loss}

    def test_step(self, batch, batch_idx):
        loss, logits = self.model(**batch)
        labels_hat = torch.argmax(logits, dim=-1)
        # print(batch['labels'])
        # print(labels_hat)
        correct_count = torch.sum((batch['labels'] == labels_hat) * batch['attention_mask'])

        if self.on_gpu:
            correct_count = correct_count.cuda(loss.device.index)

        return {"test_loss": loss, "correct_count": correct_count, "batch_size": len(batch['labels']), "total_labels": batch['attention_mask'].sum()}

    def test_end(self, outputs):
        test_acc = sum([out["correct_count"] for out in outputs]).float() / sum(out["total_labels"] for out in outputs)
        test_loss = sum([out["test_loss"] for out in outputs]) / len(outputs)
        tqdm_dict = {"test_loss": test_loss, "test_acc": test_acc}
        return {"progress_bar": tqdm_dict, "log": tqdm_dict}


    # Dataloaders

    def _preprocessor(self, instance):
        tokens = [word if not word.startswith("*") else word[1:] for word in instance.split(" ")]
        labels = [int(not word.startswith("*")) for word in instance.split(" ")]
        tokenized_tokens = list(map(self.tokenizer.tokenize, tokens))
        tokenized_labels = [[l] * len(tt) for l, tt in zip(labels, tokenized_tokens)]
        flat_tokens = [t for tt in tokenized_tokens for t in tt]
        flat_labels = [l for ll in tokenized_labels for l in ll]

        inputs = self.tokenizer.encode_plus(" ".join(tokens), add_special_tokens=True, max_length=self.config["data"]["max_len"])
        input_ids, token_type_ids = inputs["input_ids"], inputs["token_type_ids"]
        labels = [0] + flat_labels[:self.config["data"]["max_len"]-2] + [0]

        convert_ids = self.tokenizer.convert_tokens_to_ids(flat_tokens)
        assert input_ids[1:-1] == convert_ids[:len(input_ids)-2]
        assert len(input_ids) == len(labels)

        original_input_ids_len = len(input_ids)
        padding_length = self.config["data"]["max_len"] - original_input_ids_len
        input_ids = input_ids + [self.tokenizer.pad_token_id] * padding_length
        labels = labels + [0] * padding_length
        token_type_ids = token_type_ids + [self.tokenizer.pad_token_id] * padding_length
        attention_mask = [1] * original_input_ids_len + [0] * padding_length

        return {
            "labels": torch.tensor(labels).long(),  # Label*s* - vide training_step
            "input_ids": torch.tensor(input_ids),
            "attention_mask": torch.tensor(attention_mask),
            "token_type_ids": torch.tensor(token_type_ids)
        }


    def train_dataloader(self):
        train = lf.TextDataset(self.config["data"]["train_file"]).map(self._preprocessor)
        return DataLoader(train, sampler=RandomSampler(train), batch_size=self.config["model"]["batch_size"], num_workers=32)

    def val_dataloader(self):
        # val = lf.Dataset(lf.TextDataset(self.config["data"]["val_file"]).take(100)).map(self._preprocessor).save(self.config["data"]["val_cache"])
        val = lf.TextDataset(self.config["data"]["val_file"]).map(self._preprocessor)
        return DataLoader(val, sampler=SequentialSampler(val), batch_size=self.config["model"]["batch_size"], num_workers=32)

    def test_dataloader(self):
        test = lf.TextDataset(self.config["data"]["test_file"]).map(self._preprocessor)
        return DataLoader(test, sampler=SequentialSampler(test), batch_size=self.config["model"]["batch_size"], num_workers=32)