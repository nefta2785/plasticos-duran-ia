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
const body = plantilla.slice(plantilla.indexOf("<body>"), plantilla.indexOf("</body>") + "</body>".length);
const html = `<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="utf-8"/>
    <meta name="viewport" content="width=device-width, initial-scale=1"/>
    <link rel="stylesheet" href="${url(join(modulo, "static", "src", "captura.css"))}"/>
    <script src="${url(join(aqui, "simulacion.js"))}"></script>
    <script src="${url(join(aqui, "escenario.js"))}"></script>
    <script src="${url(join(modulo, "static", "src", "captura.js"))}" defer="defer"></script>
</head>
${body}
</html>`;

const temporal = mkdtempSync(join(tmpdir(), "captura-pantalla-"));
let dom;
try {
    const pagina = join(temporal, "captura.html");
    writeFileSync(pagina, html);
    dom = execFileSync(
        chrome,
        [
            "--headless=new",
            "--disable-gpu",
            // Sin --user-data-dir: en modo headless Chrome ya usa un perfil
            // temporal propio (no toca tu Chrome), y con un perfil indicado a
            // mano en macOS escribe el resultado pero no termina.
            "--no-first-run",
            "--no-default-browser-check",
            "--allow-file-access-from-files",
            "--window-size=390,844", // tamaño de celular
            "--virtual-time-budget=30000",
            "--dump-dom",
            url(pagina),
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
