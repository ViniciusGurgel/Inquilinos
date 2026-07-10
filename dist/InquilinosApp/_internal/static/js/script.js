document.querySelectorAll("form[data-confirm]").forEach((form) => {
  form.addEventListener("submit", (event) => {
    const message = form.getAttribute("data-confirm");

    if (!confirm(message)) {
      event.preventDefault();
    }
  });
});

const inquilinoSelect = document.querySelector('select[name="inquilino_id"]');
const valorCobradoInput = document.querySelector("#valorCobrado");

if (inquilinoSelect && valorCobradoInput) {
  inquilinoSelect.addEventListener("change", () => {
    const selected = inquilinoSelect.options[inquilinoSelect.selectedIndex];
    const valor = selected.getAttribute("data-valor");

    if (valor && Number(valorCobradoInput.value || 0) === 0) {
      valorCobradoInput.value = Number(valor).toFixed(2);
    }
  });
}
