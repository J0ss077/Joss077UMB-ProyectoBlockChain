# Modelado de una red neuronal simple

> Apartado para insertar en el documento maestro, a continuación de «Integración de los
> modelos» y antes de «Estado del Arte». Los títulos respetan los cinco subtítulos que
> ya tiene el documento. Las figuras van en `docs/figuras/` y el código en
> `red_neuronal/`.

## Gráfico red neuronal

![Red neuronal de la proyección](figuras/red-neuronal-general.png)

*Figura 1. La red de la proyección: 8 características de entrada, una capa oculta de 8
neuronas y 2 salidas, una por monto del próximo mes. Elaboración propia.*

## Propósito de la red neuronal dentro del sistema

La página de estadísticas cuenta lo que ya pasó: cuánto entró, cuánto salió y con quién.
Eso se calcula con aritmética exacta sobre el historial y **no lo toca ningún modelo**:
el saldo, las sumas y las gráficas siguen saliendo de la base de datos, porque son datos
que hay que poder comprobar.

La red agrega lo que la aritmética no puede dar: **una estimación de lo que va a pasar
el próximo mes** en esa cuenta. Recibe las ocho características de los últimos sesenta
días y devuelve dos montos, cuánto se espera recibir y cuánto enviar. La página los
muestra en una tarjeta aparte, junto al resumen exacto, con una línea que dice con qué
dataset se entrenó la red.

El ayudante que explica el sistema en palabras simples **no usa esta red**: ese asistente
trabaja con la API de un modelo de lenguaje, y esa es una decisión de diseño, no una
limitación. Un modelo de lenguaje redacta; esta red estima números. Mezclarlos sería
pedirle a cada uno lo que el otro hace mejor.

Dentro de la arquitectura, la red vive en un paquete propio (`red_neuronal/`) y la
aplicación la consulta desde `src/web/proyeccion.py`. No conoce PostgreSQL, no abre
conexiones y no puede modificar la cadena: sólo recibe los movimientos que la fachada ya
leyó y devuelve dos números.

## Datos de entrada y resultado esperado

**Entrada: ocho características de los últimos sesenta días.** Seis son relaciones con
lo que la cuenta recibió —no montos en pesos— y dos son el mes del año:

| Característica | Qué mide | Por qué |
| --- | --- | --- |
| `gasto_relativo` | lo enviado sobre lo recibido | Distingue una cuenta que gasta todo de una que ahorra |
| `movimientos_30d` | cuántas operaciones hubo | Una cuenta activa no se proyecta igual que una quieta |
| `neto_relativo` | el neto de los 30 días anteriores | La tendencia del mes previo |
| `colchon` | el saldo sobre lo recibido | Cuántos meses de gasto tiene disponibles |
| `movimientos_previos` | operaciones de los 30 días anteriores | Si la actividad sube o baja |
| `recibido_escala` | lo recibido, dividido por 10.000 | Conserva el tamaño de la cuenta |
| `mes_seno` y `mes_coseno` | el mes del año | Diciembre y enero quedan juntos, como en el calendario |

Trabajar con proporciones es lo que permite que **un mismo modelo sirva para un fondo
que mueve 80.000 al mes y para una cuenta que mueve 1.000**: la red aprende la forma del
comportamiento, no el tamaño. La aplicación vuelve a pesos multiplicando por lo que esa
cuenta recibió.

**Salida: dos proporciones.** Lo que se espera recibir y lo que se espera enviar el mes
siguiente, medidas sobre lo recibido este mes. La aplicación las multiplica por la escala
de la cuenta y muestra los montos. Un tope las ajusta a la realidad: el envío estimado
nunca supera el saldo disponible más lo que se espera recibir, porque el ledger tampoco
lo permitiría (`REQ-05`).

**Qué no hace.** No decide si una transacción es válida, no firma, no agrupa bloques y
no calcula saldos. Es una estimación, y se presenta como tal.

## Representación gráfica de sus capas: entrada, capa oculta y salida

![Un mes de ejemplo, capa por capa](figuras/red-neuronal-capas.png)

*Figura 2. Un ejemplo de la partición de prueba atravesando la red: las ocho características con su valor,
las ocho activaciones ocultas y los dos montos estimados, calculados con el modelo
entrenado. Elaboración propia.*

1. **Capa de entrada (8 neuronas).** Una por característica. Una capa de normalización
   la estandariza con la media y la desviación del conjunto de entrenamiento
   (`dataset/modelo/normalizacion.json`); esa capa viaja dentro del modelo, así que la
   aplicación le pasa las proporciones tal cual.
2. **Capa oculta (8 neuronas, ReLU).** Totalmente conectada con la entrada: 8 × 8 = 64
   pesos. La ReLU deja pasar lo positivo y apaga lo negativo, que es lo que permite
   combinar señales —«gasta casi todo» y «diciembre»— en lugar de mirarlas por separado.
3. **Capa de salida (2 neuronas, lineal).** Conectada con las ocho ocultas: 8 × 2 = 16
   pesos. Sin activación, porque son montos y no probabilidades. La red tiene **80 pesos**
   en total.

Durante el entrenamiento se apaga una de cada veinte neuronas ocultas (dropout), para que
una red tan chica no memorice el entrenamiento; al estimar, todas vuelven a estar activas.

## Explicación breve de su funcionamiento y de cómo apoyaría el proceso transaccional

**Los datos.** La red se entrena con el dataset de la carpeta `dataset/`: **2.500
cuentas** de un fondo de empleados durante **96 meses** (noviembre de 2018 a octubre de
2026), **814.023 transacciones** limpias y **188.111 ejemplos**. Como no existe un
historial real del fondo que se pueda publicar, el dataset es una **simulación
reproducible**: siete perfiles de comportamiento (ahorrador, frecuente, esporádico, con
primas, endeudado, comerciante y que se retira), parámetros propios por cuenta,
estacionalidad, aumentos anuales y la regla del ledger de que nadie gira más de lo que
tiene. Viene en capas —crudo con defectos reales, limpio, agregado mensual y listo para
el modelo— y en CSV, JSON Lines, Parquet, Excel y SQLite, con su diccionario de datos y
su reporte de calidad (`dataset/README.md`). Cada ejemplo se calcula con la misma
función que usa la aplicación (`caracteristicas.vector`), así que la red ve al entrenar
exactamente lo que ve en la página.

**El entrenamiento.** Los ejemplos se parten **por tiempo**: los primeros 70 % de los
cortes para entrenar, el 15 % siguiente para decidir cuándo parar y el último 15 % —meses
que el modelo nunca vio— para medir. Adam ajusta los pesos para bajar el error absoluto,
y cada ejemplo pesa según su escala: así se minimiza el error en pesos y no en
proporciones, que favorecería a las cuentas chicas. Los objetivos se acotan en cinco
veces la escala (lo hace el dataset y lo informa su reporte de calidad), porque una
cuenta que casi no recibió nada tiene una escala de pocos pesos y daría objetivos de
miles que dominarían el ajuste. El tope afecta a 9.735 ejemplos (5,2 %), sobre todo
meses de primas y de montos grandes. Por eso el dataset guarda también el monto real
sin tope (`real_recibido`, `real_enviado`), y **el error se mide contra ese monto real**,
no contra el objetivo recortado.

Una aclaración de método: el tope, la pérdida absoluta, el peso por escala y la tasa de
aprendizaje se eligieron después de una primera corrida (pérdida cuadrática, sin tope)
cuyo error de prueba se vio: 25.600 pesos, peor que las ingenuas. Lo ideal es elegir esas
decisiones sólo con validación; aquí se declara que la partición de prueba ya se había
mirado una vez.

Para saber si el modelo sirve, no alcanza con el error: hay que compararlo con dos
predicciones ingenuas. Sobre los **30.662 ejemplos de prueba**:

| Salida | Modelo | Repetir los últimos 30 días | Predecir el promedio |
| --- | --- | --- | --- |
| Recibido del próximo mes | **1.622 pesos** de error | 4.771 pesos | 1.915 pesos |
| Enviado del próximo mes | **1.268 pesos** de error | 1.622 pesos | 1.479 pesos |

El error medio es de **1.445 pesos** sobre un monto medio real de 2.733 (53 %), y en las
dos salidas gana a las dos alternativas. La ingenua de «repetir los últimos 30 días»
sale alta en lo recibido porque, cuando la cuenta no recibió nada, su escala es el saldo
y esa ingenua predice el saldo entero. Es un error alto en términos absolutos porque el
comportamiento de una cuenta mes a mes es ruidoso —un esporádico puede no moverse o
mover diez veces su ingreso—, y por eso la comparación con las ingenuas es la que dice
si la red aporta: con la misma información, se equivoca un 15 % menos que el promedio en
lo recibido y un 14 % menos en lo enviado.

**Cómo apoya el proceso transaccional.** El proceso que el proyecto protege es el
registro de una operación: la wallet firma, la transacción se valida, entra al pool, se
agrupa en un bloque encadenado y se puede verificar después. La red no interviene en
ninguna de esas etapas y no puede alterarlas. Lo que agrega es lectura: convierte el
historial en una expectativa, para que quien usa el sistema pueda anticipar si el mes que
viene va a poder cubrir sus retiros. Es información para decidir, no una decisión.

## Nota de implementación

El modelo está implementado con **TensorFlow y Keras** y corre **dentro de la
aplicación**, en cada visita a la página de estadísticas:

| Archivo | Qué hace | ¿Necesita TensorFlow? |
| --- | --- | --- |
| `red_neuronal/caracteristicas.py` | Las ocho características y la escala | No |
| `dataset/` | El dataset, sus capas y su generador (`python -m dataset.generar`) | No |
| `red_neuronal/modelo.py` | La red 8 → 8 → 2 | Sí |
| `red_neuronal/entrenar.py` | Entrena, compara con las líneas base y guarda | Sí |
| `red_neuronal/figuras.py` | Genera las figuras 1 y 2 con los valores del modelo | Sí |
| `src/web/proyeccion.py` | Carga el modelo, resume el historial real y proyecta | Sí, por dentro |

La aplicación importa TensorFlow **sólo cuando hay que proyectar**, y una vez cargado el
modelo queda en memoria. El arranque adelanta esa carga en un hilo de fondo para que la
primera visita no espere. Si TensorFlow no está instalado o el modelo no está en su
ruta, la tarjeta de proyección simplemente no aparece y el resto de la página sigue
igual: la dependencia pesada no es obligatoria para usar el prototipo.

TensorFlow va en `red_neuronal/requirements.txt` y no en el `requirements.txt` del
proyecto. Reproducir las cifras de este apartado:

```text
python3.14 -m venv .venv-tf
.venv-tf/bin/python -m pip install -r red_neuronal/requirements.txt
.venv-tf/bin/python -m dataset.generar
.venv-tf/bin/python -m red_neuronal.entrenar
.venv-tf/bin/python -m red_neuronal.figuras
```

La salida cruda de esa corrida está guardada en
`docs/evidencias/red-neuronal-entrenamiento.txt`. Resultados (semilla 2026, hasta 200
épocas con parada temprana, 53 corridas):

| Medida | Valor |
| --- | --- |
| Cuentas / meses / transacciones | 2.500 / 96 / 814.023 |
| Entrenamiento / validación / prueba | 125.667 / 31.782 / 30.662 ejemplos |
| Error absoluto medio en prueba (contra el monto real) | 1.445 pesos (53 % del monto medio) |
| Error de las líneas base en prueba | 1.915 y 1.479 pesos (promedio); 4.771 y 1.622 (últimos 30 días) |
| Pesos de la red | 80 (más los sesgos) |

**Límites declarados.** El dataset es una simulación: la proyección muestra que el
método aprende el comportamiento de un fondo con estas reglas, no afirma nada sobre el
dinero real de una organización. Con historial real, se cambia el dataset, se reentrena
con `entrenar.py` y las cifras se actualizan desde `resultados.json`.

## Referencias de este apartado

Goodfellow, I., Bengio, Y. y Courville, A. (2016). *Deep Learning*. MIT Press.
https://www.deeplearningbook.org/

Nielsen, M. (2015). *Neural Networks and Deep Learning*. Determination Press.
http://neuralnetworksanddeeplearning.com/

Rosenblatt, F. (1958). The perceptron: A probabilistic model for information storage and
organization in the brain. *Psychological Review, 65*(6), 386–408.
https://doi.org/10.1037/h0042519

TensorFlow. (s. f.). *Keras: the high-level API for TensorFlow*. Recuperado el 4 de
noviembre de 2026, de https://www.tensorflow.org/guide/keras

TensorFlow. (s. f.). *Overfit and underfit*. Recuperado el 4 de noviembre de 2026, de
https://www.tensorflow.org/tutorials/keras/overfit_and_underfit
