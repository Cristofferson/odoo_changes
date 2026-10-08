/**
 * Mosaico de la ficha: el video arranca solo y sin sonido. Chrome solo permite el
 * autoplay si la PROPIEDAD muted está puesta (el atributo que pone la plantilla no basta).
 */
import { patch } from "@web/core/utils/patch";
import { onMounted, onPatched } from "@odoo/owl";
import { ProductPage } from "@pos_self_order/app/pages/product_page/product_page";

function arrancarVideos() {
    for (const video of document.querySelectorAll(".xb_an_video")) {
        if (!video.muted) {
            video.muted = true;
        }
        if (video.paused) {
            video.play().catch(() => {});
        }
    }
}

patch(ProductPage.prototype, {
    setup() {
        super.setup(...arguments);
        onMounted(arrancarVideos);
        onPatched(arrancarVideos);
    },
});
