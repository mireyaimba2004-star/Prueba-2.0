# Planificación Estratégica Interactiva

App de Streamlit que integra en un solo lugar: el documento PAE, el Excel de matrices y el Excel
de planes de acción de Floral Chain Group. Todo **editable y conectado entre sí**.

## Cómo ejecutarla

```bash
pip install -r requirements.txt
streamlit run app.py
```
(Ejecutar desde esta carpeta para que encuentre `data/` y `assets/`.)

## Flujo de la app

1. **Carátula**: logo y datos de la empresa, editables.
2. **Barra lateral**, tres módulos:
   - **CULTURA ORGANIZACIONAL** → Problemática, Misión y Visión, Objetivos, Políticas, Valores,
     Principios, Organigrama.
   - **MATRICES PONDERACIÓN** → Holmes/MICMAC, EFI, EFE, Cadena de Valor, Perfil Competitivo,
     Ansoff, Riesgos, FODA Numérico.
   - **MAPA ESTRATÉGICO** *(nuevo)* → Balanced Scorecard: conecta la meta general, los 3 objetivos
     estratégicos, las 4 perspectivas (Financiera, Cliente, Procesos Internos, Aprendizaje y
     Crecimiento) y el Cuadro de Mando Integral con KPIs editables.
   - **PLANES** → Plan Financiero, de Marketing, de Operaciones, de Mejoras, Tecnológico,
     de Compras y de Control (todas las pestañas del Excel de planes excepto el Dashboard).
   - **SEGUIMIENTO Y CONTROL** → Gráficas de Medias (control estadístico) vinculadas en
     tiempo real al Cuadro de Mando Integral, con semáforo 🟢🟡🔴.
   - **CMI** *(nuevo)* → Estrategias 1-12 (cálculo de KPIs con datos históricos editables) en una
     sola pestaña, enlazadas en vivo con el Cuadro de Mando Integral oficial y su semáforo.
   - **SEGUIMIENTO Y CONTROL** → Gráficas de Medias (control estadístico) vinculadas en
     tiempo real al Cuadro de Mando Integral, con semáforo 🟢🟡🔴.
   - **CMI** *(nuevo)* → Estrategias 1-12 (cálculo de KPIs con datos históricos editables) en una
     sola pestaña, enlazadas en vivo con el Cuadro de Mando Integral oficial y su semáforo.

## 🗺️ Módulo MAPA ESTRATÉGICO

Ubicado en la barra lateral **entre Matrices Ponderación y Planes**. Tiene dos sub-pestañas:

- **Mapa Estratégico (cualitativo)**: la meta general del holding, desglosada por los 3 objetivos
  estratégicos, y para cada uno sus filas de **Perspectiva → Estrategia → Actividades →
  Responsable → KPI**, siguiendo la Tabla 3 del documento (Balanced Scorecard). Es una **vista de
  solo lectura** (fiel al texto original, no editable) con un **filtro por perspectiva** que
  actualiza en conjunto qué estrategias, actividades, responsable y KPI se muestran.
- **Cuadro de Mando Integral (KPIs)**: los 12 indicadores reales del holding con **Meta** y
  **Resultado editables** — el **% de Cumplimiento se recalcula solo** (Resultado ÷ Meta × 100),
  se colorea por nivel (Óptimo/Aceptable/En riesgo/Crítico) y se resume por perspectiva en un
  gráfico de barras. La interpretación identifica automáticamente el indicador más crítico y el
  más sólido, y la perspectiva con menor desempeño promedio.

## 📁 Módulo PLANES

Cada plan reconstruye el Excel original: bloques de **Tipo de estrategia** (las mismas estrategias
FO/FA/DO/DA visibles en 🔢 FODA Numérico) con sus actividades, responsable, tiempo, **costo
editable** y tipo de cuenta.

- El **TOTAL de cada plan se recalcula solo** al cambiar cualquier costo (antes era una fórmula
  fija `=SUM(...)` en Excel, ahora es una suma en vivo).
- La pestaña **📊 Resumen consolidado** suma los 7 planes en tiempo real: presupuesto total, plan
  de mayor/menor costo, gráfico de barras y de pastel — todo se actualiza si editas cualquier costo
  en cualquier plan.
- La **Misión** que se muestra en cada plan viene directamente de la pestaña 🎯 Misión y Visión
  (módulo Cultura Organizacional): si la editas ahí, cambia automáticamente aquí también — así se
  cumple que "todo el trabajo está ligado".

## 🏁 Objetivos — ponderación en cascada

```
Factor (Peso × Importancia 1-4) → Valor y %
   → Valor Total del Objetivo Táctico
      → Peso relativo dentro de su Objetivo Estratégico
         → Contribución real a la misión (Peso relativo × % del Objetivo Estratégico)
```
Mueve cualquier Peso/Importancia y toda la cadena se recalcula, incluyendo la contribución final.

## 📊 Promedios en las matrices

- **FODA Numérico**: cada submatriz (FO/FA/DO/DA) muestra debajo de la tabla editable una vista
  con columna y fila **PROMEDIO**, igual que las columnas M/X y filas 13/25 del Excel original.
- **Holmes/MICMAC**: la tabla resumen incluye una fila **PROMEDIO** de motricidad/dependencia — el
  mismo valor que define las líneas de corte del plano MICMAC.


## 🚦 Módulo SEGUIMIENTO Y CONTROL

Basado en `Grupo_3_Anexo_Estrategias.xlsx` (Hoja1: límites de control por KPI) y
`CMI_GRUPO_3_xlsxMM__1_.xlsx` (los 12 indicadores reales del Cuadro de Mando Integral, con
semáforo Cumplido/En riesgo/No cumplido). **Importante**: al reconciliar ambos archivos se
detectó que el `cuadro_mando.json` generado en una iteración anterior tenía varios indicadores
con el Resultado incorrecto (ej. "Índice de adopción de la cultura organizacional" aparecía con
95% cuando el valor real es 29.41%); se reconstruyó completo con los 12 indicadores y valores
correctos del archivo CMI real. Adicionalmente se detectó que **"Indice de Eficiencia
estructural"** (Procesos Internos) e **"Indice de Eficiencia estructura"** (Financiera) eran el
mismo KPI duplicado por un error de tipeo en el Excel original (mismo resultado 91.2%, misma
estrategia base); se conservó únicamente la versión de **Financiera**, dejando el CMI en
**12 indicadores** en total.

### Cómo se relacionan los dos archivos
- `CMI_GRUPO_3...xlsx` es la fuente de verdad de **Perspectiva, Objetivo, Plan, Indicador, Meta,
  Resultado y Responsable** (13 filas).
- `Grupo_3_Anexo_Estrategias.xlsx` (Hoja1, columnas V/W/X) aporta, para varios de esos mismos
  KPIs (identificados por el nombre exacto del indicador), sus **límites de control estadístico**:
  Límite de Control Superior (UCL), Límite Central y Límite de Control Inferior (LCL) — es decir,
  la **gráfica de medias** de cada indicador.
- 5 de los 12 indicadores tenían límites válidos en el anexo; los otros 7 tenían errores de
  referencia (`#REF!`) o texto en vez de números en la fórmula original de Excel, así que la app
  genera una **banda sintética de control (±15 puntos porcentuales sobre el resultado actual)**
  y lo marca explícitamente como "🧮 Límites estimados" para que quede claro que no proviene del
  anexo.

### Las dos pestañas están sincronizadas
- **📈 Gráficas de Medias**: un gráfico de bala (bullet chart) por KPI muestra la zona en control
  (verde, entre LCL y UCL) y el resultado actual. Debajo, un **control deslizante de Resultado**
  y un campo de **Meta** — ambos editables.
- **🚦 Cuadro de Mando Integral**: tabla de solo lectura que recalcula al instante el
  % de Cumplimiento (Resultado ÷ Meta × 100) y el **semáforo** (🟢 ≥90% Cumplido ·
  🟡 70-89% En riesgo · 🔴 <70% No cumplido) usando los mismos valores que acabas de mover en
  Gráficas de Medias — ambas pestañas leen y escriben el mismo estado compartido, así que un
  cambio en una se refleja de inmediato en la otra.


## 🚦 Módulo CMI

Basado en `Grupo_3_Anexo_Estrategias.xlsx` (hojas "Estrategia 1" a "Estrategia 12") y
`CMI_GRUPO_3_bien_xlsxMM.xlsx` (el Cuadro de Mando Integral oficial, 12 indicadores). Al
analizar ambos archivos se descubrió que **cada una de las 12 hojas "Estrategia N" corresponde
exactamente a uno de los 12 indicadores del CMI** (verificado por fórmula/variables, no solo por
nombre — por ejemplo, "Estrategia 4" se llama "Índice de Cumplimiento de Estándares de Calidad"
pero sus variables son idénticas a la fórmula del CMI para "Índice de mejoras en procesos de
postcosecha y normas ambientales").

### Las dos pestañas de este módulo

- **📐 Estrategias 1-12** (una sola pestaña, con un expansor por estrategia): cada una trae su
  serie histórica editable (2022-2025, o 5 departamentos × 5 años en los KPI de tipo "n=5"). Con
  esos datos se recalculan automáticamente:
  - el **KPI de cada año** (razón simple o suma de variables, según la fórmula original),
  - el **Promedio**, el **Rango**, y
  - los límites de control **LCS / LCC / LCI** (fórmula X-bar & R: `LCS = Promedio + A2×Rango`,
    `LCI = Promedio − A2×Rango`, usando la constante A2 real del anexo según el tamaño de muestra).
  - Un gráfico de línea muestra el KPI anual contra su banda de control.
  - El **valor del último año** de cada Estrategia es el que alimenta el Resultado de su
    indicador correspondiente en el CMI.

- **🚦 Cuadro de Mando Integral**: Perspectiva, Objetivo, Plan, Indicador, Fórmula, **Meta**
  (editable), **Resultado** (tomado en vivo de Estrategias 1-12), **% de Cumplimiento** y
  **semáforo** (🟢 ≥90% Cumplido · 🟡 70-89% En riesgo · 🔴 <70% No cumplido) — todo recalculado
  al instante. **Cambia cualquier valor histórico en Estrategias 1-12 y el semáforo del CMI se
  actualiza solo**, sin necesidad de tocar nada en la segunda pestaña.

## Estructura

```
app.py                # Aplicación principal (carátula + barra lateral + 3 módulos)
data/*.json            # Valores originales de los 3 documentos fuente, editables
assets/logo.png
assets/organigrama.png
requirements.txt
```

## Notas

- Cada pestaña tiene un botón **"↩️ Restaurar valores originales"**.
- Los pesos deberían sumar 1.00 en EFI, EFE, MPC y en las tablas de factores de Objetivos.
- Puedes agregar o quitar filas (actividades, factores, riesgos, etc.) con el botón "+" de cada tabla.
- Todos los totales, gráficos e interpretaciones se recalculan automáticamente al cambiar cualquier
  valor numérico, en cualquier parte de la app.
