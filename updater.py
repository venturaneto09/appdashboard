#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import subprocess
import threading
import zipfile
import requests
import customtkinter as ctk
from tkinter import messagebox

# ===================== CONFIGURAÇÕES DO UPDATER =====================
# URL do version.json no seu repositório GitHub (arquivo raw)
# Formato: https://raw.githubusercontent.com/SEU_USUARIO/SEU_REPO/main/version.json
VERSION_CHECK_URL = "https://raw.githubusercontent.com/venturaneto09/appdashboard/main/version.json"

# Versão atual — mude isso a cada novo build antes de gerar o .exe
CURRENT_VERSION = "1.0.0"

# Timeout para requisições de atualização
UPDATE_TIMEOUT = 15
# ====================================================================


def get_current_exe_path() -> str:
    """Retorna o caminho do executável atual (ou script em dev)."""
    if getattr(sys, "frozen", False):
        return sys.executable
    return os.path.abspath(__file__)


def _do_replace_and_restart(new_exe_path: str, current_exe: str):
    """
    Cria um script .bat temporário que:
    1. Aguarda o processo atual encerrar
    2. Substitui o executável antigo pelo novo
    3. Inicia o novo executável
    4. Se deleta
    """
    bat_path = os.path.join(os.path.dirname(current_exe), "_update_helper.bat")
    bat_content = f"""@echo off
ping 127.0.0.1 -n 3 > nul
move /Y "{new_exe_path}" "{current_exe}"
start "" "{current_exe}"
del "%~f0"
"""
    with open(bat_path, "w", encoding="cp1252") as f:
        f.write(bat_content)

    subprocess.Popen(
        ["cmd.exe", "/c", bat_path],
        creationflags=subprocess.CREATE_NO_WINDOW,
        close_fds=True,
    )
    sys.exit(0)


class UpdateWindow(ctk.CTkToplevel):
    """Janela de progresso de download da atualização."""

    def __init__(self, master, version: str, download_url: str):
        super().__init__(master)
        self.title("Atualização Disponível")
        self.geometry("420x180")
        self.resizable(False, False)
        self.grab_set()

        # Centralizar
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"420x180+{(sw-420)//2}+{(sh-180)//2}")

        ctk.CTkLabel(
            self,
            text=f"Nova versão disponível: {version}",
            font=ctk.CTkFont(size=15, weight="bold"),
        ).pack(pady=(18, 6))

        self.status_label = ctk.CTkLabel(self, text="Baixando atualização...")
        self.status_label.pack(pady=4)

        self.progress = ctk.CTkProgressBar(self, width=370)
        self.progress.set(0)
        self.progress.pack(pady=8)

        self._download_url = download_url
        self._thread = threading.Thread(target=self._download, daemon=True)
        self._thread.start()

    def _download(self):
        current_exe = get_current_exe_path()
        exe_dir = os.path.dirname(current_exe)
        tmp_zip = os.path.join(exe_dir, "_update.zip")
        tmp_exe = current_exe + ".new"

        try:
            r = requests.get(self._download_url, stream=True, timeout=UPDATE_TIMEOUT)
            r.raise_for_status()

            total = int(r.headers.get("Content-Length", 0))
            downloaded = 0

            with open(tmp_zip, "wb") as f:
                for chunk in r.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total > 0:
                            self.after(0, self.progress.set, downloaded / total)

            # Extrai o .exe do zip
            with zipfile.ZipFile(tmp_zip, "r") as z:
                exe_files = [n for n in z.namelist() if n.endswith(".exe")]
                if not exe_files:
                    raise Exception("Nenhum .exe encontrado no arquivo zip.")
                z.extract(exe_files[0], exe_dir)
                extracted = os.path.join(exe_dir, exe_files[0])
                os.replace(extracted, tmp_exe)

            os.remove(tmp_zip)
            self.after(0, self._on_done, tmp_exe, current_exe)

        except Exception as e:
            for f in [tmp_zip, tmp_exe]:
                if os.path.exists(f):
                    os.remove(f)
            self.after(0, self._on_error, str(e))

    def _on_done(self, tmp_path: str, current_exe: str):
        self.status_label.configure(text="Download concluído! Reiniciando...")
        self.progress.set(1)
        self.after(800, lambda: _do_replace_and_restart(tmp_path, current_exe))

    def _on_error(self, msg: str):
        self.status_label.configure(text=f"Erro: {msg}", text_color="red")
        self.after(3000, self.destroy)


def check_for_updates(master_window) -> bool:
    """
    Verifica se existe uma atualização disponível.
    - Se sim: abre a janela de download e retorna True (o app deve aguardar/fechar).
    - Se não: retorna False (o app continua normalmente).

    O version.json deve ter o formato:
    {
        "version": "1.0.1",
        "download_url": "https://exemplo.com/painel_v1.0.1.exe"
    }
    """
    try:
        r = requests.get(VERSION_CHECK_URL, timeout=UPDATE_TIMEOUT)
        r.raise_for_status()
        data = r.json()

        latest_version = data.get("version", "")
        download_url = data.get("download_url", "")

        if not latest_version or not download_url:
            return False

        if latest_version == CURRENT_VERSION:
            return False

        # Há atualização — pergunta ao usuário
        answer = messagebox.askyesno(
            "Atualização Disponível",
            f"Uma nova versão está disponível: {latest_version}\n"
            f"Versão atual: {CURRENT_VERSION}\n\n"
            "Deseja atualizar agora?",
        )
        if answer:
            UpdateWindow(master_window, latest_version, download_url)
            return True

        return False

    except Exception:
        # Falha silenciosa — não bloqueia o app se não tiver internet/servidor
        return False
