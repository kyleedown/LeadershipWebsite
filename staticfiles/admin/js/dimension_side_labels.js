// Updates the "side" dropdown labels in DimensionResult inline rows
// to show the dimension's actual pole names instead of generic Left/Right.
(function () {
    const API = '/quizzes/api/dimension-names/';
    const cache = {};

    async function fetchNames(dimId) {
        if (cache[dimId]) return cache[dimId];
        const r = await fetch(`${API}?dimension_id=${dimId}`);
        const data = r.ok ? await r.json() : null;
        if (data) cache[dimId] = data;
        return data;
    }

    function updateSideSelect(sideSelect, names) {
        if (!names) return;
        for (const opt of sideSelect.options) {
            if (opt.value === 'left')  opt.text = names.left;
            if (opt.value === 'right') opt.text = names.right;
        }
    }

    function initRow(row) {
        const dimSelect  = row.querySelector('select[id*="-dimension"]');
        const sideSelect = row.querySelector('select[id*="-side"]');
        if (!dimSelect || !sideSelect) return;

        if (dimSelect.value) {
            fetchNames(dimSelect.value).then(n => updateSideSelect(sideSelect, n));
        }

        dimSelect.addEventListener('change', () => {
            if (dimSelect.value) {
                fetchNames(dimSelect.value).then(n => updateSideSelect(sideSelect, n));
            } else {
                // Reset to generic labels when no dimension selected
                for (const opt of sideSelect.options) {
                    if (opt.value === 'left')  opt.text = 'Left';
                    if (opt.value === 'right') opt.text = 'Right';
                }
            }
        });
    }

    function initAll() {
        document.querySelectorAll('[id^="dimension_results-"][id$="-row"]').forEach(initRow);
        // Also catch rows that don't follow the -row suffix
        document.querySelectorAll('.dynamic-dimension_results').forEach(initRow);
    }

    function setup() {
        initAll();
        const group = document.getElementById('dimension_results-group');
        if (group) {
            new MutationObserver(mutations => {
                mutations.forEach(m => m.addedNodes.forEach(node => {
                    if (node.nodeType === 1) initRow(node);
                }));
            }).observe(group, { childList: true, subtree: true });
        }
    }

    // Defer until after Django admin's own inline scripts have run.
    function scheduleSetup() {
        setTimeout(setup, 0);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', scheduleSetup);
    } else {
        scheduleSetup();
    }
})();
