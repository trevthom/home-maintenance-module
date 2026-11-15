/* Home Maintenance: show the repeat fields only for recurring tasks and ask
   before deleting. The screens work without JavaScript; this is polish. */
(function () {
  'use strict';

  var app = document.querySelector('.mnt-app');
  if (!app) {
    return;
  }

  var repeatRow = app.querySelector('[data-repeat-row]');

  function selectedRepeat() {
    var checked = app.querySelector('input[name="repeat"]:checked');
    return checked ? checked.value : 'once';
  }

  function syncRepeatRow() {
    if (repeatRow) {
      repeatRow.hidden = selectedRepeat() !== 'recurring';
    }
  }

  Array.prototype.forEach.call(
    app.querySelectorAll('input[name="repeat"]'),
    function (input) {
      input.addEventListener('change', syncRepeatRow);
    }
  );
  syncRepeatRow();

  app.addEventListener('submit', function (event) {
    var form = event.target.closest('form[data-confirm]');
    if (!form) {
      return;
    }
    if (!window.confirm(form.getAttribute('data-confirm') || 'Delete this?')) {
      event.preventDefault();
    }
  });
})();
