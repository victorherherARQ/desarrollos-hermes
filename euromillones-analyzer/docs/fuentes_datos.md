# Fuentes de datos - Euromillones

## Investigación realizada

### Fuentes evaluadas

| Fuente | URL | Estado | Notas |
|---|---|---|---|
| **GitHub: daowa89/lottery-archive** | https://raw.githubusercontent.com/daowa89/lottery-archive/main/eu/euromillions/results.csv | ✅ **FUENTE PRIMARIA** | 1951 sorteos, 2004-02-13 a 2026-06-23 |
| Wikipedia ES | https://es.wikipedia.org/wiki/Euromillones | ⚠️ Sin tabla de resultados | Solo info general del juego |
| Wikipedia EN | https://en.wikipedia.org/wiki/EuroMillions | ⚠️ Sin tabla completa | Solo records de jackpots |
| loteriasyapuestas.es | https://www.loteriasyapuestas.es/es/la-euromillones/resultados | ❌ HTTP 403 | Requiere JS/auth |
| euro-millions.com | https://www.euro-millions.com | ❌ Caído (HTTP 000) | Dominio no responde |
| national-lottery.co.uk | https://www.national-lottery.co.uk/results/euromillions | ⚠️ HTML moderno | Requiere render JS |

### Fuente primaria: CSV de GitHub

**URL**: https://raw.githubusercontent.com/daowa89/lottery-archive/main/eu/euromillions/results.csv

**Estructura**:
```
date,n1,n2,n3,n4,n5,s1,s2
2004-02-13,16,29,32,36,41,7,9
...
2026-06-23,3,33,36,45,46,5,6
```

- **Total registros**: 1951 sorteos
- **Rango**: 2004-02-13 a 2026-06-23 (22.4 años)
- **Frecuencia**: ~87 sorteos/año (esperado 104 = 2/semana × 52 semanas; pérdida de ~17% posiblemente por festivos o falta de actualización)
- **Días**: 1159 viernes + 787 martes + 5 especiales
- **Sin duplicados**
- **Sin números repetidos por sorteo**
- **Rangos correctos**: números 1-50, estrellas 1-12

### ⚠️ Limitación importante: NO hay info de país

El CSV **no incluye qué país sorteó**. Esto requiere ajustar el plan original.

#### ¿Por qué no importa tanto?

**Euromillones es un sorteo transnacional**: los mismos 5 números + 2 estrellas se sortean simultáneamente en los 9 países participantes (España, Francia, Reino Unido, Irlanda, Austria, Bélgica, Suiza, Portugal, Luxemburgo). Es **un único sorteo**, no 9.

El "país sorteante" afecta a:
- **Idioma del boleto** (cosmético)
- **Divisa del premio** (GBP, EUR, CHF)
- **Asignación de botes especiales** (superdraws) que algunos países sí organizan

Pero **los números sorteados son los mismos para todos los países cada martes/viernes**. No hay una "ruleta española" vs "ruleta francesa".

#### ¿Qué hacer entonces?

El "análisis por país" del plan original se replantea como:

**Opción A (recomendada)**: Eliminar la dimensión "país" del análisis. Los datos no la tienen y añadirla requeriría scraping complejo con poco valor.

**Opción B**: Buscar si en los datos hay sorteos donde un país fue "sede" del superdraw. Esto requiere cruzar con otro dataset y es marginal.

**Opción C**: Buscar si en los datos hay sorteos en fechas específicas (por ejemplo, superdraws de UK) que tuvieran dinámicas distintas.

**Decisión**: Adoptamos **Opción A**. El análisis estadístico se hace sobre el universo completo de sorteos. Si en algún momento se necesita info de país, lo añadimos como mejora.

### Decisiones finales

1. **Fuente de datos**: CSV de GitHub (daowa89/lottery-archive)
2. **Volumen**: 1951 sorteos (suficiente para análisis estadístico significativo)
3. **Sin info de país** — se replantea el análisis
4. **Idiomas**: informe en español
5. **Validación cruzada**: comparar frecuencias esperadas (uniforme) vs observadas como sanity check
