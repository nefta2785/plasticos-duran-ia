#!/usr/bin/env node
/* Corre las pruebas de pantalla de /captura en Chrome sin interfaz (headless).
 *
 * Uso, desde la raíz del proyecto en la Mac:
 *     node custom-addons/duran_captura_tianguis/tests/pantalla/correr.mjs
 *     node custom-addons/duran_captura_tianguis/tests/pantalla/correr.mjs --detalle
 *
 * No usa Odoo ni la base de datos: arma la página con el <body> de la
 * plantilla real (views/captura_templates.xml), el CSS y el JS reales del
 * módulo, y simulacion.js en lugar del servidor. Luego recorre la pantalla con
 * escenario.js.
 *
 * Termina con código 0 si todo pasa y 1 si algo falla. Chrome se busca en la
 * ruta normal de macOS; para otra ruta: CHROME="/ruta/a/chrome" node correr.mjs */
import { execFileSync } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const aqui = dirname(fileURLToPath(import.meta.url));
const modulo = resolve(aqui, "..", "..");
const chrome = process.env.CHROME || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const detalle = process.argv.includes("--detalle");

if (!existsSync(chrome)) {
    console.error(`No se encontró Chrome en: ${chrome}\nIndica la ruta con CHROME="/ruta/a/chrome".`);
    process.exit(2);
}

const url = (ruta) => pathToFileURL(ruta).href;
const plantilla = readFileSync(join(modulo, "views", "captura_templates.xml"), "utf8");
const body = plantilla.slice(plantilla.indexOf("<body"), plantilla.indexOf("</body>") + "</body>".length);
// El servidor decide si hay botón "Salir" (data-salir en <body>): la página se
// arma dos veces, como la ve un administrador y como la ve el usuario de tianguis.
const ETIQUETA_BODY = `<body t-att-data-salir="'1' if puede_salir else None">`;
if (!body.startsWith(ETIQUETA_BODY)) {
    console.error(`La plantilla ya no empieza el <body> con: ${ETIQUETA_BODY}\nActualiza correr.mjs.`);
    process.exit(1);
}
const pagina = (etiqueta) => `<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="utf-8"/>
    <meta name="viewport" content="width=device-width, initial-scale=1"/>
    <meta name="theme-color" content="#0b3d91"/>
    <link rel="stylesheet" href="${url(join(modulo, "static", "src", "captura.css"))}"/>
    <script src="${url(join(aqui, "simulacion.js"))}"></script>
    <script src="${url(join(aqui, "escenario.js"))}"></script>
    <script src="${url(join(modulo, "static", "src", "captura.js"))}" defer="defer"></script>
</head>
${etiqueta}${body.slice(ETIQUETA_BODY.length)}
</html>`;

// Chrome sin ventana no dibuja a menos de 500 px de ancho aunque se le pida
// --window-size=393: la página se carga dentro de un marco (iframe) del tamaño
// exacto del iPhone 16, 393 x 852, que sí es su ancho real de pantalla. El
// marco copia los resultados a la página de afuera para --dump-dom. Hay un
// marco por cada forma de la página, uno después del otro; los resultados se
// juntan.
const ANCHO = 393;
const ALTO = 852;
const marco = `<!DOCTYPE html>
<html lang="es">
<head><meta charset="utf-8"/></head>
<body style="margin: 0">
    <script>
        // Una forma de la página a la vez: los marcos de una misma página
        // comparten el historial ("atrás") y se estorbarían.
        const paginas = ["captura.html", "tianguis.html"];
        const textos = [];
        function siguiente() {
            const marco = document.createElement("iframe");
            marco.src = paginas[textos.length];
            marco.style.cssText = "display: block; width: ${ANCHO}px; height: ${ALTO}px; border: 0";
            document.body.append(marco);
            const revisar = setInterval(() => {
                const resultado = marco.contentDocument?.getElementById("resultado-prueba");
                if (resultado) {
                    clearInterval(revisar);
                    textos.push(resultado.textContent);
                    marco.remove();
                    if (textos.length < paginas.length) {
                        siguiente();
                    } else {
                        const copia = document.createElement("pre");
                        copia.id = "resultado-prueba";
                        copia.textContent = textos.join("\\n");
                        document.body.append(copia);
                    }
                }
            }, 100);
        }
        siguiente();
    </script>
</body>
</html>`;

const temporal = mkdtempSync(join(tmpdir(), "captura-pantalla-"));
let dom;
try {
    writeFileSync(join(temporal, "captura.html"), pagina('<body data-salir="1">')); // administrador o gerente
    writeFileSync(join(temporal, "tianguis.html"), pagina("<body>")); // usuario de tianguis
    const rutaMarco = join(temporal, "marco.html");
    writeFileSync(rutaMarco, marco);
    dom = execFileSync(
        chrome,
        [
            "--headless=new",
            "--disable-gpu",
            // Barras de desplazamiento como en el celular (Android las dibuja
            // encima, sin quitar ancho). El Chrome de escritorio 154.0.8037.98
            // las pone clásicas, de 15px: en las pantallas que se deslizan el
            // ancho útil bajaba a 378px y todo lo alineado a la derecha se
            // corría. (--enable-features=OverlayScrollbar no tiene efecto en macOS.)
            "--hide-scrollbars",
            // Sin --user-data-dir: en modo headless Chrome ya usa un perfil
            // temporal propio (no toca tu Chrome), y con un perfil indicado a
            // mano en macOS escribe el resultado pero no termina.
            "--no-first-run",
            "--no-default-browser-check",
            "--allow-file-access-from-files",
            "--window-size=500,900", // el ancho de celular lo da el marco (ver arriba)
            "--virtual-time-budget=60000",
            "--dump-dom",
            url(rutaMarco),
        ],
        {
            encoding: "utf8",
            maxBuffer: 20 * 1024 * 1024,
            stdio: ["ignore", "pipe", "ignore"],
            timeout: 120000, // nunca quedarse colgado: 2 minutos como máximo
            killSignal: "SIGKILL",
        }
    );
} catch (error) {
    console.error(
        error.code === "ETIMEDOUT"
            ? "Chrome no terminó en 2 minutos; se detuvo la prueba."
            : `No se pudo correr Chrome: ${error.message}`
    );
    process.exitCode = 1;
} finally {
    rmSync(temporal, { recursive: true, force: true });
}
if (dom === undefined) {
    process.exit(1);
}

const encontrado = dom.match(/<pre id="resultado-prueba">([\s\S]*?)<\/pre>/);
if (!encontrado) {
    console.error("La pantalla no produjo resultados (¿error de JavaScript al arrancar?).");
    process.exit(1);
}
const lineas = encontrado[1]
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&amp;/g, "&")
    .split("\n")
    .filter(Boolean);
const fallas = lineas.filter((linea) => !linea.startsWith("OK"));

for (const linea of detalle ? lineas : fallas) {
    console.log(linea);
}
console.log(`\nPruebas de pantalla: ${lineas.length - fallas.length} OK, ${fallas.length} con falla, de ${lineas.length}.`);
process.exit(fallas.length ? 1 : 0);
