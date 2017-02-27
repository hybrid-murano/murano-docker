horizon.modals.modal_spinner = function (text) {
// Adds a spinner with the desired text in a modal window.
var template = horizon.templates.compiled_templates["#spinner-modal"];
horizon.modals.spinner = $(template.render({text: text}));
horizon.modals.spinner.appendTo("#modal_wrapper");
horizon.modals.spinner.modal({backdrop: 'static'});
var div = $('<div id="manageone-spin" class="manageone-spin"></div>');
horizon.modals.spinner.find(".modal-body").wrapInner(div);
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

horizon.datatables.redraw_az = function () {
  var AWS = $("<div>").addClass("loading_gif").append($("<img>").attr("src", STATIC_URL + "themes/hybrid/img/aws-icon.png").attr("height", "48").attr("width", "48")).html();
  var VCLOUD = $("<div>").addClass("loading_gif").append($("<img>").attr("src", STATIC_URL + "themes/hybrid/img/vcloud-icon.png").attr("height", "48").attr("width", "48")).html();
  var FS = $("<div>").addClass("loading_gif").append($("<img>").attr("src", STATIC_URL + "themes/hybrid/img/fs-icon.png").attr("height", "48").attr("width", "48")).html();
  var HWS = $("<div>").addClass("loading_gif").append($("<img>").attr("src", STATIC_URL + "themes/hybrid/img/hws-icon.png").attr("height", "48").attr("width", "48")).html();
  var OPENSTACK = $("<div>").addClass("loading_gif").append($("<img>").attr("src", STATIC_URL + "themes/hybrid/img/openstack.png").attr("height", "48").attr("width", "48")).html();
  var OTC = $("<div>").addClass("loading_gif").append($("<img>").attr("src", STATIC_URL + "themes/hybrid/img/otc.png").attr("height", "48").attr("width", "48")).html();
  function _redraw_az() {
    var az_type = $(this).text().split('--');
    if(az_type.length > 1) {
      az_last = az_type[1].split(':');
      tail = (az_last.length>1)?(":"+az_last[1]):"";
      cloud = az_last[0].replace(/(\s*$)/g, "");
      //if(cloud == 'fusionsphere')
      //    cloud = 'openstack'
      switch(cloud) {
      case "vcloud":
          $(this).html(VCLOUD+az_type[0]+"("+gettext(cloud)+")"+tail);
          break;
      case "fusionsphere":
          $(this).html(FS+az_type[0]+"("+gettext(cloud)+")"+tail);
          break;
      case "aws":
    	  $(this).html(AWS+az_type[0]+"("+gettext(cloud)+")"+tail);
    	  break;
      case "hws":
          $(this).html(HWS+az_type[0]+"("+gettext(cloud)+")"+tail);
          break;
      case "openstack":
          $(this).html(OPENSTACK+az_type[0]+"("+gettext(cloud)+")"+tail);
          break;
      case "otc":
          $(this).html(OTC+az_type[0]+"("+gettext(cloud)+")"+tail);
          break;
      }
    }
  }
  $(".az_field").each(_redraw_az);
  $(".az_field").removeClass("az_field");
}

horizon.datatables.update = function () {
  horizon.datatables.redraw_az();
  var $rows_to_update = $('tr.status_unknown.ajax-update'),
    rows_to_update = $rows_to_update.length;
  if ( rows_to_update > 0 ) {
    var interval = $rows_to_update.attr('data-update-interval'),
      $table = $rows_to_update.closest('table'),
      submit_in_progress = $table.closest('form').attr('data-submitted'),
      decay_constant = $table.attr('decay_constant');

    // Do not update this row if the action column is expanded or the form
    // is in the process of being submitted. If we update the row while the
    // form is still submitting any disabled action buttons would potentially
    // be enabled again, allowing for multiple form submits.
    if ($rows_to_update.find('.actions_column .btn-group.open').length ||
        submit_in_progress) {
      // Wait and try to update again in next interval instead
      setTimeout(horizon.datatables.update, interval);
      // Remove interval decay, since this will not hit server
      $table.removeAttr('decay_constant');
      return;
    }
    // Trigger the update handlers.
    $rows_to_update.each(function() {
      var $row = $(this),
        $table = $row.closest('table.datatable');
      horizon.ajax.queue({
        url: $row.attr('data-update-url'),
        error: function (jqXHR) {
          switch (jqXHR.status) {
            // A 404 indicates the object is gone, and should be removed from the table
            case 404:
              // Update the footer count and reset to default empty row if needed
              var row_count, colspan, template, params;

              // existing count minus one for the row we're removing
              row_count = horizon.datatables.update_footer_count($table, -1);

              if(row_count === 0) {
                colspan = $table.find('.table_column_header th').length;
                template = horizon.templates.compiled_templates["#empty_row_template"];
                params = {
                    "colspan": colspan,
                    no_items_label: gettext("No items to display.")
                };
                var empty_row = template.render(params);
                $row.replaceWith(empty_row);
              } else {
                $row.remove();
              }
              // Reset tablesorter's data cache.
              $table.trigger("update");
              // Enable launch action if quota is not exceeded
              horizon.datatables.update_actions();
              break;
            default:
              console.log(gettext("An error occurred while updating."));
              $row.removeClass("ajax-update");
              $row.find("i.ajax-updating").remove();
              break;
          }
        },
        success: function (data) {
          var $new_row = $(data);

          if ($new_row.hasClass('status_unknown')) {
            var $container = $(document.createElement('div'))
              .addClass('horizon-pending-bar');

            var $progress = $(document.createElement('div'))
              .addClass('progress progress-striped active')
              .appendTo($container);

            $(document.createElement('div'))
              .addClass('progress-bar')
              .css("width", "100%")
              .appendTo($progress);

            // if action/confirm is required, show progress-bar with "?"
            // icon to indicate user action is required
            if ($new_row.find('.btn-action-required').length > 0) {
              $(document.createElement('span'))
                .addClass('fa fa-question-circle horizon-pending-bar-icon')
                .appendTo($container);
            }
            $new_row.find("td.status_unknown:last").wrapInner($container);
          }

          // Only replace row if the html content has changed
          if($new_row.html() !== $row.html()) {

            // Directly accessing the checked property of the element
            // is MUCH faster than using jQuery's helper method
            var $checkbox = $row.find('.table-row-multi-select');
            if($checkbox.length && $checkbox[0].checked) {
              // Preserve the checkbox if it's already clicked
              $new_row.find('.table-row-multi-select').prop('checked', true);
            }
            $row.replaceWith($new_row);

            // TODO(matt-borland, tsufiev): ideally we should solve the
            // problem with not-working angular actions in a content added
            // by jQuery via replacing jQuery insert with Angular insert.
            // Should address this in Newton release
            recompileAngularContent($table);

            // Reset tablesorter's data cache.
            $table.trigger("update");
            // Reset decay constant.
            $table.removeAttr('decay_constant');
            // Check that quicksearch is enabled for this table
            // Reset quicksearch's data cache.
            if ($table.attr('id') in horizon.datatables.qs) {
              horizon.datatables.qs[$table.attr('id')].cache();
            }
          }
          horizon.datatables.redraw_az();
        },
        complete: function () {
          // Revalidate the button check for the updated table
          horizon.datatables.validate_button();
          rows_to_update--;
          // Schedule next poll when all the rows are updated
          if ( rows_to_update === 0 ) {
            // Set interval decay to this table, and increase if it already exist
            if(decay_constant === undefined) {
              decay_constant = 1;
            } else {
              decay_constant++;
            }
            $table.attr('decay_constant', decay_constant);
            // Poll until there are no rows in an "unknown" state on the page.
            var next_poll = interval * decay_constant;
            // Limit the interval to 30 secs
            if(next_poll > 30 * 1000) { next_poll = 30 * 1000; }
            setTimeout(horizon.datatables.update, next_poll);
          }
        }
      });
    });
  }
}

horizon.datatables.update_actions = function() {
    var $actions_to_update = $('.btn-launch.ajax-update, .btn-create.ajax-update');
    $actions_to_update.each(function() {
      var $action = $(this);
      horizon.ajax.queue({
        url: $action.attr('data-update-url'),
        error: function () {
          horizon.utils.log(gettext("An error occurred while updating."));
        },
        success: function (data) {
          var $new_action = $(data);

          // Only replace row if the html content has changed
          if($new_action.html() != $action.html()) {
            $action.replaceWith($new_action);
            horizon.datatables.redraw_az();
          }
        }
      });
    });
  }