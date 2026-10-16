"""Partition a module's legacy cache while retaining the original owner's data."""
from types import SimpleNamespace

from fastapi import HTTPException

from .data import digest


class AccountStore:
    def __init__(self, store, prefix):
        self.store, self.prefix = store, prefix

    def read(self, key, default=None):
        return self.store.read(self.prefix + key, default)

    def write(self, key, value):
        self.store.write(self.prefix + key, value)

    def delete(self, key):
        self.store.delete(self.prefix + key)


class AccountCache:
    def __init__(self, context, provider):
        self.context, self.provider = context, provider
        if context.store.read("library_owner") is None:
            context.store.write("library_owner", self.owner())

    def owner(self):
        return digest(self.context.auth.get_status(self.provider)["account_revision"])

    def capture(self):
        owner = self.owner()
        original = owner == self.context.store.read("library_owner")
        values = dict(vars(self.context))
        values.update(
            store=AccountStore(self.context.store, "" if original else "account:" + owner + ":"),
            data_dir=self.context.data_dir if original else self.context.data_dir / "accounts" / owner,
            account_owner=owner,
        )
        return SimpleNamespace(**values)

    def check(self, captured):
        if self.owner() != captured.account_owner:
            raise HTTPException(409, "账号已切换，请刷新当前页面。")
