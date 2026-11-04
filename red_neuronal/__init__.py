"""La red neuronal de la proyección de estadísticas, hecha con TensorFlow.

El paquete existe para la actividad de modelado de la red neuronal. Responde una sola
pregunta: **¿cuánto se espera recibir y enviar el próximo mes en esta cuenta?** La
página de estadísticas lo muestra en su tarjeta de proyección.

| Archivo | Qué hace | ¿Necesita TensorFlow? |
| ------- | -------- | --------------------- |
| `caracteristicas.py` | Las ocho características de entrada y la escala para volver a pesos | No |
| `serie.py` | La serie sintética de 240 meses con la que se entrena | No |
| `modelo.py` | Arma y compila la red 8 → 8 → 2 | Sí |
| `entrenar.py` | Entrena, compara con dos predicciones ingenuas y guarda modelo y resumen | Sí |
| `figuras.py` | Genera las figuras del apartado con los valores del modelo | Sí |

TensorFlow va en `red_neuronal/requirements.txt` y **no** en el `requirements.txt` del
proyecto: la aplicación, sus pruebas y el lint tienen que seguir instalándose y
corriendo sin los cientos de megas del motor. Sin TensorFlow, lo único que no se puede
hacer es entrenar la red; la página de estadísticas simplemente no muestra la tarjeta de
proyección y el resto del prototipo funciona igual.

Cómo se reproduce:

```text
python3.14 -m venv .venv-tf
.venv-tf/bin/python -m pip install -r red_neuronal/requirements.txt
.venv-tf/bin/python -m red_neuronal.entrenar
.venv-tf/bin/python -m red_neuronal.figuras
```
"""
