<script>
    $(document).ready(function() {
        $("#{{ formGridInstance['table_id'] }}").UIBootgrid({
            search: '/api/openconnect/general/searchInstance/',
            get: '/api/openconnect/general/getInstance/',
            set: '/api/openconnect/general/setInstance/',
            add: '/api/openconnect/general/addInstance',
            del: '/api/openconnect/general/delInstance/',
            toggle: '/api/openconnect/general/toggleInstance/'
        });

        $("#reconfigureAct").SimpleActionButton();

        updateServiceControlUI('openconnect');

        var currentLog = null;

        function renderLogList(rows) {
            var html = '';
            rows.forEach(function(r) {
                var cls = (r.interface === currentLog) ? ' class="active"' : '';
                html += '<li' + cls + '><a href="javascript:void(0)" data-iface="' + r.interface + '">' +
                        '<i class="fa fa-fw fa-' + (r.running ? 'check-circle text-success' : 'times-circle text-danger') + '"></i> ' +
                        r.interface + '</a></li>';
            });
            $('#logTabs').html(html);
            $('#logTabs a').on('click', function() {
                loadLog($(this).data('iface'));
            });
        }

        function refreshStatus() {
            $.ajax('/api/openconnect/general/status', {
                dataType: 'json',
                success: function(data) {
                    var rows = data.rows || [];
                    var html = '';
                    rows.forEach(function(r) {
                        var cls = r.running ? 'fa fa-check-circle text-success' : 'fa fa-times-circle text-danger';
                        html += '<tr><td><i class="' + cls + '"></i> ' + r.interface + '</td>' +
                                '<td>' + r.server + '</td><td>' + r.state + '</td></tr>';
                    });
                    if (rows.length === 0) {
                        html = '<tr><td colspan="3" class="text-muted">{{ lang._("No instances configured.") }}</td></tr>';
                    }
                    $('#statusRows').html(html);
                    renderLogList(rows);
                    if (currentLog === null && rows.length > 0) {
                        loadLog(rows[0].interface);
                    }
                }
            });
        }

        function loadLog(iface) {
            currentLog = iface;
            $('#logTabs li').removeClass('active').filter(function() {
                return $(this).find('a').data('iface') === iface;
            }).addClass('active');
            $('#logTitle').text('Log: ' + iface);
            $.ajax('/api/openconnect/general/log/' + iface, {
                dataType: 'json',
                success: function(data) {
                    var text = (data.lines || []).join('\n');
                    $('#logBody').text(text || '{{ lang._("(log is empty)") }}');
                    var el = document.getElementById('logBody');
                    if (el) { el.scrollTop = el.scrollHeight; }
                }
            });
        }

        refreshStatus();
        setInterval(function() {
            refreshStatus();
            if (currentLog !== null) { loadLog(currentLog); }
        }, 10000);

        // tab navigation with hash
        if (window.location.hash != "") {
            $('#maintabs a[href="' + window.location.hash + '"]').tab('show');
        }
        $('#maintabs a').on('shown.bs.tab', function (e) {
            history.pushState(null, null, e.target.hash);
        });
        $(window).on('hashchange', function () {
            $('#maintabs a[href="' + window.location.hash + '"]').tab('show');
        });
    });
</script>

<ul class="nav nav-tabs" data-tabs="tabs" id="maintabs">
    <li class="active"><a data-toggle="tab" id="tab_instances" href="#pane_instances">{{ lang._('Instances') }}</a></li>
    <li><a data-toggle="tab" id="tab_status" href="#pane_status">{{ lang._('Status') }}</a></li>
    <li><a data-toggle="tab" id="tab_logs" href="#pane_logs">{{ lang._('Logs') }}</a></li>
</ul>

<div class="tab-content content-box tab-content">
    <div id="pane_instances" class="tab-pane fade in active">
        {{ partial('layout_partials/base_bootgrid_table', formGridInstance)}}
    </div>
    <div id="pane_status" class="tab-pane fade in">
        <table class="table table-striped">
            <thead><tr><th style="width:200px;">{{ lang._('Instance') }}</th><th>{{ lang._('Server') }}</th><th style="width:220px;">{{ lang._('State') }}</th></tr></thead>
            <tbody id="statusRows"><tr><td colspan="3">{{ lang._('Loading...') }}</td></tr></tbody>
        </table>
    </div>
    <div id="pane_logs" class="tab-pane fade in">
        <div class="row">
            <div class="col-md-3">
                <ul class="nav nav-pills nav-stacked" id="logTabs"></ul>
            </div>
            <div class="col-md-9">
                <h4 id="logTitle">{{ lang._('Select an instance') }}</h4>
                <pre id="logBody" style="max-height:520px;overflow:auto;white-space:pre-wrap;"></pre>
            </div>
        </div>
    </div>
</div>

{{ partial('layout_partials/base_apply_button', {'data_endpoint': '/api/openconnect/service/reconfigure', 'data_service_widget': 'openconnect'}) }}

{{ partial('layout_partials/base_dialog',['fields':formDialogInstance,'id':formGridInstance['edit_dialog_id'],'label':lang._('OpenConnect Instance')])}}