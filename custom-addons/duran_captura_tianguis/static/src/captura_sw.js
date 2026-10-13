/* Service worker de /captura, para que Chrome la ofrezca como app instalable.
 * Lo sirve la ruta /captura/sw.js (controllers/main.py), no /static, para que
 * su alcance pueda ser /captura.
 *
 * NO guarda nada: cada petición va directo a la red, igual que sin service
 * worker. Así una actualización del módulo se ve en cuanto se recarga y, sin
 * señal, la pantalla falla igual que en el navegador. */
self.addEventListener("fetch", (event) => {
    event.respondWith(fetch(event.request));
});
