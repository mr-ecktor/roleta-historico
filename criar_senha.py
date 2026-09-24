"""
Gera o bloco de login (usuário + senha criptografada) para colar nos "Secrets" do site.
Uso:  python criar_senha.py
"""

import getpass
import hashlib
import secrets

usuario = input("Usuário: ").strip()
senha = getpass.getpass("Senha (não aparece enquanto digita): ")
if senha != getpass.getpass("Repita a senha: "):
    raise SystemExit("As senhas não conferem.")

sal = secrets.token_hex(16)
senha_hash = hashlib.pbkdf2_hmac("sha256", senha.encode(), bytes.fromhex(sal), 200_000).hex()

print("\nCopie o bloco abaixo (inclusive a linha [login]):\n")
print("[login]")
print(f'usuario = "{usuario}"')
print(f'sal = "{sal}"')
print(f'senha_hash = "{senha_hash}"')
