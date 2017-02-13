horizon.modals.modal_spinner = function (text) {
  // Adds a spinner with the desired text in a modal window.
  var template = horizon.templates.compiled_templates["#spinner-modal"];
  horizon.modals.spinner = $(template.render({text: text}));
  horizon.modals.spinner.appendTo("#modal_wrapper");
  horizon.modals.spinner.modal({backdrop: 'static'});
  //var div = $('<div id="manageone-spin" class="manageone-spin"></div>');
  //horizon.modals.spinner.find(".modal-body").wrapInner(div);
  horizon.modals.spinner.find(".modal-body").spin(horizon.conf.spinner_options.modal);
};

horizon.datatables.update_footer_count = function (el, modifier) {
  var $el = $(el),
    $browser, $footer, row_count, footer_text_template, footer_text;
  if (!modifier) {
    modifier = 0;
  }
  // code paths for table or browser footers...
  /*$browser = $el.closest("#browser_wrapper");
  if ($browser.length) {
    $footer = $browser.find('.tfoot span.content_table_count');
  }
  else {
    $footer = $el.find('tfoot span.table_count');
  }*/
  row_count = $el.find('tbody tr:visible').length + modifier - $el.find('.empty').length;
  /*if (row_count) {
    footer_text_template = ngettext("Displaying %s item", "Displaying %s items", row_count);
    footer_text = interpolate(footer_text_template, [row_count]);
  } else {
    footer_text = '';
  }
  $footer.text(footer_text);*/
  return row_count;
};
