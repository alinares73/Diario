# Actualización mensual de la app de la Biblia

Convierte los `.pdb` de Almudi en la app web (Biblia + Comentarios + libros enlazados), comprueba
que **todos** los enlaces funcionan y deja en tu carpeta de GitHub solo los archivos que han cambiado.
No necesita instalar ninguna librería, solo Python 3.9 o superior.

## Estructura
```
actualizador/
  actualizar.py      <- el script que ejecutas
  config.json        <- rutas (ver abajo)
  pdb/               <- aquí van los 50 .pdb (se sobrescriben los 4 nuevos cada mes)
  src/, plantillas/  <- código y plantillas (no tocar)
  trabajo/           <- caché interna (se crea sola; se puede borrar sin miedo)
  informe.txt        <- resumen de la última ejecución
```

## Primera vez (una sola vez)
1. Descomprime la carpeta `actualizador` donde quieras y ábrela en VSCode (*Archivo > Abrir carpeta*).
2. Copia los 50 `.pdb` que te envió Almudi a la carpeta `pdb/`.
3. Abre `config.json` y pon en `"destino"` la ruta de tu copia local del repositorio de GitHub
   (la carpeta que contiene `index.html` y `sw.js`). Ejemplo: `"destino": "C:/Users/tu/Documentos/Almud"`.
   Si todavía no tienes copia local, déjalo como está (`salida/app`) y copia el resultado a mano esta primera vez.
4. Ejecuta (ver abajo). La primera vez tarda unos 15 minutos porque lee los 50 libros.

## Cada mes
1. Descarga los 4 archivos nuevos (`Biblia.pdb`, `Cartas.pdb`, `Comentarios.pdb`, `Leon14.pdb`) y **cópialos sobre
   los antiguos en `pdb/`** (mismo nombre, "Reemplazar"). No hay que tocar nada más.
2. En VSCode pulsa **F5** (elige "Actualizar app (mensual)") o, en el terminal (Ctrl+ñ):
   `python actualizar.py`
3. El script te dice qué `.pdb` han cambiado, solo vuelve a leer esos, reconstruye lo necesario y
   comprueba todos los enlaces. Si hay **algún enlace roto se detiene sin tocar tu carpeta de destino**.
4. Mira `informe.txt` (enlaces comprobados, cuántos archivos han cambiado). 
5. En VSCode, panel **Control de código fuente** (Ctrl+Mayús+G): verás solo los archivos modificados.
   Escribe un mensaje ("Actualización de mayo"), *Commit* y *Sync/Push*. GitHub Pages publica la nueva versión.

**No hay que sobrescribir ni borrar la carpeta de la app**: el script la actualiza él solo (añade, modifica y
borra únicamente lo que ha cambiado), así Git sube pocos archivos.

## Qué verán los usuarios
La app guarda los datos en el móvil. Al abrirla con conexión detecta la versión nueva, la descarga
y muestra un aviso "Hay contenido nuevo disponible – Recargar".

## Si algo falla
- `Faltan estos .pdb`: falta algún libro en `pdb/` (hacen falta los 50, con el nombre original).
- `enlaces rotos`: no se publica nada. Envía `informe.txt` y la salida del terminal para revisarlo.
- Para empezar de cero: borra la carpeta `trabajo/` o ejecuta con `--forzar`.
- Si Almudi añade o quita libros enlazados, hay que editar la lista `APP_DOCS` de `actualizar.py`.
