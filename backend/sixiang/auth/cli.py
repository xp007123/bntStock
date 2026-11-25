"""账号管理命令行（在服务器上运行）。

    python -m sixiang.auth.cli create-admin --username 管理员名 --phone 13800000000
    python -m sixiang.auth.cli list [--status pending]
    python -m sixiang.auth.cli approve <用户ID>

密码通过交互输入，不出现在命令行参数或日志里。
"""
from __future__ import annotations

import argparse
import getpass
import sys

from ..config import load_settings
from .db import make_engine
from .service import AuthError, AuthService


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="sixiang.auth.cli")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create-admin"); c.add_argument("--username", required=True); c.add_argument("--phone", required=True)
    ls = sub.add_parser("list"); ls.add_argument("--status")
    ap_ = sub.add_parser("approve"); ap_.add_argument("uid", type=int)
    args = ap.parse_args(argv)
    svc = AuthService(make_engine(load_settings().db_url()))
    try:
        if args.cmd == "create-admin":
            pw = getpass.getpass("设置密码：")
            confirm = getpass.getpass("再次输入：")
            user = svc.register(args.username, args.phone, pw, confirm, status="active", is_admin=True)
            print(f"已创建管理员 {user.username}（ID {user.id}）")
        elif args.cmd == "list":
            for u in svc.list_users(args.status):
                print(u["id"], u["username"], u["phone"], u["status"], "管理员" if u["is_admin"] else "", u["created_at"])
        elif args.cmd == "approve":
            from .service import User
            svc.set_status(args.uid, "active", User(0, "cli", "", "active", True), "命令行审核")
            print("已通过")
    except (AuthError, KeyError) as exc:
        print(f"失败：{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
