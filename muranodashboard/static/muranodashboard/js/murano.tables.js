/*    Copyright (c) 2015 Mirantis, Inc.

      Licensed under the Apache License, Version 2.0 (the "License"); you may
      not use this file except in compliance with the License. You may obtain
      a copy of the License at

      http://www.apache.org/licenses/LICENSE-2.0

      Unless required by applicable law or agreed to in writing, software
      distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
      WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
      License for the specific language governing permissions and limitations
      under the License.
*/

// In some cases successfull update events can stack up in case we have lots of apps in an env.
// This might lead to a situation when lots of reloads are scheduled simultaneously.
// The following variable forces reload to be called only once.
var reloadCalled = false;

horizon.datatables.update = function () {
  var $rows_to_update = $('tr.status_unknown.ajax-update'),
  rows_to_update = $rows_to_update.length;
  if ( rows_to_update > 0 ) {
    var interval = 60000, //$rows_to_update.attr('data-update-interval'),
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
      //horizon.ajax.queue({
        //url: $row.attr('data-update-url'),
        //success: function (data) {
          //var $new_row = $(data);
          var $new_row = $row;
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
          //if($new_row.html() !== $row.html()) {

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
          //}
        //}
      //});
    });
//        complete: function () {
          // Revalidate the button check for the updated table
          horizon.datatables.validate_button();
          //rows_to_update--;
          // Schedule next poll when all the rows are updated
          //if ( rows_to_update === 0 ) {
            // Set interval decay to this table, and increase if it already exist
            if(decay_constant === undefined) {
              decay_constant = 1;
            } else {
              decay_constant++;
            }
            $table.attr('decay_constant', decay_constant);
            // Poll until there are no rows in an "unknown" state on the page.
            var next_poll = interval * decay_constant;
            // Limit the interval to 120 secs
            if(next_poll > 120 * 1000) { next_poll = 120 * 1000; }
            setTimeout(function() {location.reload(false)}, next_poll);
          //}
//        }
  }
}

$(function() {
  "use strict";
  $("table#services.datatable").on("update", function () {
    // If every component has finished installing (with error or success): reloads the page.
    var $rowsToUpdate = $(this).find('tr.status_unknown.ajax-update');
    if ($rowsToUpdate.length === 0) {
      if (reloadCalled === false) {
        reloadCalled = true;
        location.reload(true);
      }
    }
  });
});

var reloadEnvironmentCalled = false;

$(function() {
  "use strict";
  $("table#environments").on("update", function () {
    var $environmentsRows = $(this).find('tbody tr:visible').not('.empty');
    if ($environmentsRows.length === 0) {
      if (reloadEnvironmentCalled === false) {
        reloadEnvironmentCalled = true;
        location.reload(true);
      }
    }
  });
});
