# 🎬 Guion del vídeo — Predictor del Mundial 2026 (WillCarlo)

> Vídeo para mi canal explicando el predictor que monté con Claude Code, inspirado en
> el **Oloráculo de Dot Dager**. Duración objetivo: ~7–9 min.
>
> **Pendiente de rellenar:** `[tu línea personal sobre Dot Dager]` y `[LINK DE TU REPO]`.

---

## Datos clave (para no equivocarme en cámara)

- **Youtuber original:** Dot Dager — `@DotDager` → youtube.com/@DotDager (138 K subs, full-stack senior).
- **Vídeo donde lo presenta:** "PROGRAMÉ UN MONSTRUO" → youtube.com/watch?v=cvPeS0qAikw
- **Proyecto original (open source):** Oloráculo → github.com/MarianoVilla/Oloraculo (.NET 9 / Blazor / EF Core / SQLite).
- **Lo mío:** un port/remake con otro stack, hecho con Claude Code.

---

## 0. Gancho (15–20 s)

> "He montado un predictor del Mundial 2026 que simula el torneo miles de veces y te
> dice qué probabilidad tiene cada selección de pasar de fase, llegar a cuartos o ser
> campeona. Y lo más loco: no lo programé yo línea a línea… lo construí hablando con
> una IA. Pero antes de nada, esto no es idea mía."

*(En pantalla: la app corriendo, la tabla de probabilidades moviéndose.)*

---

## 1. Crédito y recomendación a Dot Dager (30–45 s) — IMPORTANTE, al principio

> "Todo esto está inspirado en el **Oloráculo**, un proyecto de **Dot Dager**, un crack
> full-stack al que sigo. Lo presentó en un vídeo que se llama **'Programé un monstruo'**
> —os lo dejo en la descripción junto a su canal— y os recomiendo MUCHo que os paséis:
> `[tu línea personal: por qué te gusta su contenido]`.
>
> Él lo hizo en .NET con Blazor y lo tiene público en GitHub. De ahí saqué la lógica y
> los datos de partida. Yo lo que hice fue cogerlo y montar mi propia versión, para
> aprender."

*(En pantalla: su canal @DotDager y, si quieres, un clip cortito de "Programé un monstruo" citándolo.)*

---

## 2. Qué es esto (30 s)

> "Es básicamente un remake de su Oloráculo. Misma matemática, misma idea, pero
> reescrito de cero en otra tecnología. Tiene varias pantallas: un laboratorio para
> enfrentar dos selecciones, la fase de grupos con resultados reales en directo, y
> simulaciones de todo el torneo."

*(B-roll: ir pasando por las pestañas Real → Laboratorio.)*

---

## 3. Con qué lo monté: Claude Code (45–60 s)

> "Lo construí con **Claude Code**, una IA de programación con la que trabajas en el
> terminal: le dices qué quieres y va escribiendo y modificando el código contigo.
>
> El proyecto de Dot Dager estaba en **.NET 9 y Blazor**, y yo lo porté a:
> - **Backend en Python con FastAPI**
> - **Base de datos MariaDB**
> - **Frontend en TypeScript con Vite**
> - y todo levantado con **Docker** en un solo comando.
>
> Y lo interesante es que muchas decisiones las fui discutiendo con la IA: por qué un
> equipo salía en tal posición, si tenía sentido, cómo enseñar las estadísticas… casi
> como programar en pareja."

*(B-roll: el terminal de Claude Code trabajando, o un `docker compose up`.)*

---

## 4. 🔑 De dónde sale la información (60–90 s) — LA PARTE QUE MÁS ME IMPORTA

> "¿Y de dónde saca los datos para predecir? De cuatro fuentes, todas públicas:
>
> 1. **El ranking Elo de las selecciones**, de **eloratings.net** (lo tomo vía
>    international-football.net). Es un número que mide la fuerza de cada equipo según
>    sus resultados.
> 2. **El ranking FIFA oficial**, con los puntos de cada selección.
> 3. **Casi 50.000 partidos internacionales reales, desde 1872 hasta hoy** — un dataset
>    histórico abierto. Con eso el modelo aprende cuántos goles suele marcar y encajar
>    cada equipo.
> 4. Y para los resultados **en directo del Mundial**, se conecta al **marcador público
>    de ESPN**, sin API key. Cada minuto busca los partidos finalizados y los que se
>    están jugando."

*(En pantalla: ir mostrando cada web una por una. Enlaces en la descripción.)*

---

## 5. Cómo predice, en simple (45–60 s)

> "Con todo eso arma una especie de **escalera de modelos**. Para cada partido mezcla:
> el ranking FIFA, el Elo, la forma reciente, y sobre todo un **modelo de goles tipo
> Poisson** —la matemática que usan las casas de apuestas— entrenado con esos 50.000
> partidos. De ahí salen las probabilidades de victoria, empate y derrota, y el marcador
> más probable.
>
> Y para el torneo entero, **simula el Mundial miles de veces** (un Montecarlo) y cuenta
> con qué frecuencia cada selección gana su grupo, pasa de fase o llega a la final."

*(B-roll: la pestaña Laboratorio enfrentando dos equipos y mostrando la escalera.)*

---

## 6. ⭐ La parte que mola: estadísticas de fase de grupos (60–90 s)

> "Para mí lo más interesante no es decir 'quién será campeón' —eso es casi imposible—,
> sino las **estadísticas de la fase de grupos**. Con los resultados reales que ya hay,
> simula los partidos que faltan y te dice, por ejemplo, qué probabilidad tiene cada
> selección de **clasificarse a dieciseisavos**, cuántos puntos espera sacar, y la
> probabilidad de terminar 1º, 2º, 3º o 4º de su grupo.
>
> Mirad este grupo: este equipo ganó su primer partido, pero el modelo le da solo un X%
> de pasar porque todavía le quedan los dos cocos del grupo. Eso sí que da conversación."

*(B-roll: la pantalla "Fase de grupos" con las barras de posición y los puntos esperados.
Recuerda: con 48 equipos pasan los 2 primeros de cada grupo + los 8 mejores terceros.)*

---

## 7. La parte honesta: el cuadro (40–60 s) — convierto la duda en punto fuerte

> "Ahora seré sincero, porque me parece lo más honesto: la parte del **cuadro de
> eliminatorias es la que menos me convence**, y os explico por qué. El modelo es tan
> 'prudente' que en cruces parejos casi todo le sale 50-50, una moneda al aire. Así que
> el cuadro 'más probable' tiende a dar siempre el mismo favorito por márgenes mínimos,
> y si lo dejas al azar te puede salir una final rarísima.
>
> No es un fallo: es que acertar 7 partidos seguidos de eliminación directa es casi
> imposible. Por eso me quedo con lo que de verdad aporta valor: las **probabilidades
> de la fase de grupos**, que sí se apoyan en datos sólidos."

---

## 8. Cierre / CTA (20–30 s)

> "Así que eso: un proyecto para aprender, inspirado en el monstruo que programó
> **Dot Dager** —pasaos por su canal, link abajo—, montado con IA y datos públicos.
>
> Si os interesa que suba el código o haga un tutorial de cómo lo hice con Claude Code,
> decídmelo en comentarios. ¡Nos vemos en el próximo!"

---

## 📝 Texto para la descripción del vídeo

```
🔮 Predictor del Mundial 2026 — inspirado en el Oloráculo de Dot Dager

▶ Canal de Dot Dager (¡suscríbete!): https://youtube.com/@DotDager
▶ Su vídeo "Programé un monstruo": https://youtube.com/watch?v=cvPeS0qAikw
▶ Proyecto original (Oloráculo, GitHub): https://github.com/MarianoVilla/Oloraculo
▶ Mi versión: https://github.com/canalenguillem/willCarlo

Construido con: Claude Code · Python + FastAPI · MariaDB · TypeScript/Vite · Docker

Fuentes de datos:
• Ratings Elo — eloratings.net / international-football.net
• Ranking FIFA oficial
• ~49.000 partidos internacionales (1872–2026), dataset abierto
• Resultados en vivo — marcador público de ESPN
```

---

## Notas y avisos

- **Dataset histórico:** son 49.445 partidos (1872–2026). Las columnas coinciden con el
  clásico dataset abierto "International football results from 1872 to present". Si lo
  citas en la descripción, enlaza esa fuente.
- **Terminología:** con 48 equipos, la primera ronda eliminatoria es la de 32
  ("dieciseisavos"): 2 primeros de cada grupo + 8 mejores terceros. Tu enfoque de "quién
  pasa de fase" es justo lo más sólido del modelo.
- **Tono:** Dot Dager es argentino y desenfadado; un guiño a su humor ("contador serial
  de chistes") puede quedar simpático sin forzar.
- **Pendiente tuyo:** `[tu línea personal sobre Dot Dager]` y `[LINK DE TU REPO]`.
