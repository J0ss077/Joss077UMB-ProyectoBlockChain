"""REQ-21: ningún secreto se versiona.

La cadena de conexión y la clave maestra viven en el entorno, y `.env` —el
archivo que las lleva en local— está ignorado por git y no versionado.
"""
import subprocess


def test_req_21_env_esta_ignorado_y_no_versionado():
    """`git check-ignore` reconoce `.env` y `git ls-files` no lo tiene registrado."""
    assert subprocess.run(["git", "check-ignore", "-q", ".env"]).returncode == 0
    registrado = subprocess.run(
        ["git", "ls-files", "--error-unmatch", ".env"], capture_output=True
    )
    assert registrado.returncode != 0
