(function () {
    function getBranchValueForField(field) {
        var branchSelectId = field.getAttribute('data-engineer-branch');
        if (!branchSelectId) {
            return '';
        }
        var branchSelect = document.getElementById(branchSelectId);
        return branchSelect ? (branchSelect.value || '') : '';
    }

    function fetchEngineerOptions(select) {
        var endpoint = select.getAttribute('data-engineer-endpoint');
        if (!endpoint) {
            return;
        }
        var branchName = getBranchValueForField(select);
        var selectedValue = select.getAttribute('data-selected-engineer') || '';
        var url = endpoint + '?branch=' + encodeURIComponent(branchName);
        fetch(url, {
            headers: {
                'Accept': 'application/json'
            }
        })
            .then(function (response) {
                return response.json();
            })
            .then(function (payload) {
                if (!payload || !payload.success || !Array.isArray(payload.items)) {
                    return;
                }
                var placeholder = select.getAttribute('data-placeholder') || 'Select Engineer';
                var options = ['<option value="">' + placeholder + '</option>'];
                payload.items.forEach(function (item) {
                    var value = String(item.id || '');
                    var selected = value === String(selectedValue) ? ' selected' : '';
                    options.push('<option value="' + value + '"' + selected + '>' + item.username + '</option>');
                });
                select.innerHTML = options.join('');
            })
            .catch(function () {
            });
    }

    function bindEngineerLoaders() {
        document.querySelectorAll('[data-engineer-endpoint][data-engineer-branch]').forEach(function (select) {
            var branchSelect = document.getElementById(select.getAttribute('data-engineer-branch'));
            if (!branchSelect || branchSelect.__onsiteEngineersBound) {
                return;
            }
            branchSelect.__onsiteEngineersBound = true;
            branchSelect.addEventListener('change', function () {
                document.querySelectorAll('[data-engineer-branch="' + branchSelect.id + '"]').forEach(fetchEngineerOptions);
            });
            document.querySelectorAll('[data-engineer-branch="' + branchSelect.id + '"]').forEach(fetchEngineerOptions);
        });
    }

    function hideEngineerResults(input) {
        var listId = input.getAttribute('data-engineer-list');
        var datalist = listId ? document.getElementById(listId) : null;
        var resultsId = input.getAttribute('data-engineer-results');
        var results = resultsId ? document.getElementById(resultsId) : null;
        if (datalist) {
            datalist.innerHTML = '';
        }
        if (results) {
            results.innerHTML = '';
            results.hidden = true;
        }
    }

    function clearEngineerSelection(input, clearText) {
        var hiddenId = input.getAttribute('data-engineer-target');
        var hiddenInput = hiddenId ? document.getElementById(hiddenId) : null;
        if (hiddenInput) {
            hiddenInput.value = '';
            hiddenInput.removeAttribute('data-selected-label');
        }
        if (clearText) {
            input.value = '';
        }
        input.setCustomValidity('');
        hideEngineerResults(input);
    }

    function renderEngineerMatches(input, items) {
        var listId = input.getAttribute('data-engineer-list');
        var hiddenId = input.getAttribute('data-engineer-target');
        var resultsId = input.getAttribute('data-engineer-results');
        var datalist = listId ? document.getElementById(listId) : null;
        var results = resultsId ? document.getElementById(resultsId) : null;
        var hiddenInput = hiddenId ? document.getElementById(hiddenId) : null;
        if ((!datalist && !results) || !hiddenInput) {
            return;
        }
        if (datalist) {
            datalist.innerHTML = '';
        }
        if (results) {
            results.innerHTML = '';
        }
        input.__onsiteEngineerMatchMap = {};
        if (!items.length) {
            if (results) {
                var emptyState = document.createElement('div');
                emptyState.className = 'onsite-typeahead-empty';
                emptyState.textContent = 'No matching coordinator found';
                results.appendChild(emptyState);
                results.hidden = false;
            }
            return;
        }
        items.forEach(function (item) {
            var value = String(item.username || '');
            if (datalist) {
                var option = document.createElement('option');
                option.value = value;
                datalist.appendChild(option);
            }
            input.__onsiteEngineerMatchMap[value.trim().toUpperCase()] = String(item.id || '');
            if (results) {
                var button = document.createElement('button');
                button.type = 'button';
                button.className = 'onsite-typeahead-option';
                button.textContent = value;
                button.addEventListener('click', function () {
                    hiddenInput.value = String(item.id || '');
                    hiddenInput.setAttribute('data-selected-label', value);
                    input.value = value;
                    input.setCustomValidity('');
                    hideEngineerResults(input);
                });
                results.appendChild(button);
            }
        });
        if (results) {
            results.hidden = false;
        }
        var normalizedCurrentValue = (input.value || '').trim().toUpperCase();
        if (normalizedCurrentValue && input.__onsiteEngineerMatchMap[normalizedCurrentValue]) {
            hiddenInput.value = input.__onsiteEngineerMatchMap[normalizedCurrentValue];
            hiddenInput.setAttribute('data-selected-label', input.value || '');
        }
    }

    function searchEngineers(input) {
        var endpoint = input.getAttribute('data-engineer-search-endpoint');
        var hiddenId = input.getAttribute('data-engineer-target');
        var hiddenInput = hiddenId ? document.getElementById(hiddenId) : null;
        if (!endpoint || !hiddenInput) {
            return;
        }
        var query = (input.value || '').trim();
        var selectedLabel = hiddenInput.getAttribute('data-selected-label') || '';
        if (query !== selectedLabel) {
            hiddenInput.value = '';
        }
        if (!query) {
            hideEngineerResults(input);
            input.setCustomValidity('');
            return;
        }
        var url = endpoint
            + '?branch=' + encodeURIComponent(getBranchValueForField(input))
            + '&q=' + encodeURIComponent(query)
            + '&limit=8';
        fetch(url, {
            headers: {
                'Accept': 'application/json'
            }
        })
            .then(function (response) {
                return response.json();
            })
            .then(function (payload) {
                if (!payload || !payload.success || !Array.isArray(payload.items)) {
                    hideEngineerResults(input);
                    return;
                }
                renderEngineerMatches(input, payload.items);
            })
            .catch(function () {
                hideEngineerResults(input);
            });
    }

    function bindEngineerSearchInputs() {
        document.querySelectorAll('[data-engineer-search-endpoint][data-engineer-target]').forEach(function (input) {
            var branchSelectId = input.getAttribute('data-engineer-branch');
            var branchSelect = branchSelectId ? document.getElementById(branchSelectId) : null;
            var hiddenId = input.getAttribute('data-engineer-target');
            var hiddenInput = hiddenId ? document.getElementById(hiddenId) : null;

            if (hiddenInput && input.value) {
                hiddenInput.setAttribute('data-selected-label', input.value);
            }

            input.addEventListener('input', function () {
                input.setCustomValidity('');
                if (hiddenInput) {
                    var exactMatchId = (input.__onsiteEngineerMatchMap || {})[(input.value || '').trim().toUpperCase()] || '';
                    if (exactMatchId) {
                        hiddenInput.value = exactMatchId;
                        hiddenInput.setAttribute('data-selected-label', input.value || '');
                    } else if ((hiddenInput.getAttribute('data-selected-label') || '') !== (input.value || '')) {
                        hiddenInput.value = '';
                    }
                }
                searchEngineers(input);
            });
            input.addEventListener('change', function () {
                if (hiddenInput) {
                    var exactMatchId = (input.__onsiteEngineerMatchMap || {})[(input.value || '').trim().toUpperCase()] || '';
                    if (exactMatchId) {
                        hiddenInput.value = exactMatchId;
                        hiddenInput.setAttribute('data-selected-label', input.value || '');
                    }
                }
            });
            input.addEventListener('focus', function () {
                if ((input.value || '').trim()) {
                    searchEngineers(input);
                }
            });
            input.addEventListener('blur', function () {
                window.setTimeout(function () {
                    var typedValue = (input.value || '').trim();
                    var isRequired = input.getAttribute('data-engineer-required') === '1';
                    if (hiddenInput && typedValue && !hiddenInput.value) {
                        input.setCustomValidity('Select an engineer from the search results');
                    } else if (hiddenInput && !typedValue && !isRequired) {
                        input.setCustomValidity('');
                    }
                }, 150);
            });

            if (branchSelect && !branchSelect.__onsiteEngineerSearchBound) {
                branchSelect.__onsiteEngineerSearchBound = true;
                branchSelect.addEventListener('change', function () {
                    document.querySelectorAll('[data-engineer-search-endpoint][data-engineer-branch="' + branchSelect.id + '"]').forEach(function (field) {
                        clearEngineerSelection(field, true);
                    });
                });
            }

            var form = input.closest('form');
            if (form && !form.__onsiteEngineerValidationBound) {
                form.__onsiteEngineerValidationBound = true;
                form.addEventListener('submit', function (event) {
                    var valid = true;
                    form.querySelectorAll('[data-engineer-search-endpoint][data-engineer-target]').forEach(function (field) {
                        var targetId = field.getAttribute('data-engineer-target');
                        var target = targetId ? document.getElementById(targetId) : null;
                        var typedValue = (field.value || '').trim();
                        var selectedValue = target ? (target.value || '').trim() : '';
                        var isRequired = field.getAttribute('data-engineer-required') === '1';
                        field.setCustomValidity('');
                        if ((isRequired || typedValue) && !selectedValue) {
                            field.setCustomValidity('Select an engineer from the search results');
                            valid = false;
                        }
                    });
                    if (!valid) {
                        event.preventDefault();
                        form.reportValidity();
                    }
                });
            }
        });
    }

    function bindFilterFormReset() {
        document.querySelectorAll('[data-onsite-filter-reset]').forEach(function (button) {
            button.addEventListener('click', function () {
                var formId = button.getAttribute('data-onsite-filter-reset');
                var form = document.getElementById(formId);
                if (!form) {
                    return;
                }
                var defaultStatus = form.getAttribute('data-onsite-default-status') || 'ALL';
                form.querySelectorAll('input, select').forEach(function (field) {
                    var resetValue = field.getAttribute('data-onsite-reset-value');
                    if (field.name === 'status') {
                        field.value = defaultStatus;
                        return;
                    }
                    if (resetValue !== null) {
                        field.value = resetValue;
                        return;
                    }
                    if (field.tagName === 'SELECT') {
                        field.selectedIndex = 0;
                    } else if (field.type !== 'hidden') {
                        field.value = '';
                    }
                });
                form.submit();
            });
        });
    }

    function setFilterPanelState(panel, expanded) {
        var button = panel.querySelector('[data-onsite-filter-toggle]');
        var body = panel.querySelector('[data-onsite-filter-panel-body]');
        var label = panel.querySelector('[data-onsite-filter-toggle-label]');
        if (!button || !body || !label) {
            return;
        }
        panel.classList.toggle('is-open', expanded);
        button.setAttribute('aria-expanded', expanded ? 'true' : 'false');
        body.setAttribute('aria-hidden', expanded ? 'false' : 'true');
        label.textContent = expanded ? 'Hide Filters' : 'Show Filters';
    }

    function bindFilterPanelToggles() {
        document.querySelectorAll('[data-onsite-filter-panel]').forEach(function (panel) {
            var button = panel.querySelector('[data-onsite-filter-toggle]');
            if (!button || button.__onsiteFilterToggleBound) {
                return;
            }
            button.__onsiteFilterToggleBound = true;
            setFilterPanelState(panel, panel.classList.contains('is-open'));
            button.addEventListener('click', function () {
                setFilterPanelState(panel, !panel.classList.contains('is-open'));
            });
        });
    }

    function parseMoneyValue(value) {
        var parsed = Number(value || 0);
        return Number.isFinite(parsed) ? parsed : 0;
    }

    function bindCreateForms() {
        document.querySelectorAll('[data-onsite-create-form]').forEach(function (form) {
            if (form.__onsiteCreateModeBound) {
                return;
            }
            form.__onsiteCreateModeBound = true;

            var entryTypeField = form.querySelector('[data-onsite-entry-type]');
            var submitLabel = form.querySelector('[data-onsite-submit-label]');

            if (!entryTypeField) {
                return;
            }

            function setRequiredState(field, required) {
                if (!field) {
                    return;
                }
                if (required) {
                    field.setAttribute('required', 'required');
                } else {
                    field.removeAttribute('required');
                    field.setCustomValidity('');
                }
            }

            function updateCreateFormState() {
                var activeMode = entryTypeField.value === 'Lead' ? 'Lead' : 'Onsite';

                form.querySelectorAll('[data-onsite-mode-field]').forEach(function (block) {
                    block.hidden = block.getAttribute('data-onsite-mode-field') !== activeMode;
                });

                form.querySelectorAll('[data-onsite-required-on]').forEach(function (field) {
                    setRequiredState(field, field.getAttribute('data-onsite-required-on') === activeMode);
                });

                if (submitLabel) {
                    submitLabel.textContent = activeMode === 'Lead' ? 'Create Lead' : 'Create Onsite Call';
                }
            }

            entryTypeField.addEventListener('change', updateCreateFormState);
            updateCreateFormState();
        });
    }

    function bindCloseForms() {
        document.querySelectorAll('[data-onsite-close-form]').forEach(function (form) {
            if (form.__onsiteCloseBound) {
                return;
            }
            form.__onsiteCloseBound = true;

            var finalStatusField = form.querySelector('[data-onsite-close-status]');
            var completionTypeField = form.querySelector('[data-onsite-completion-type]');
            var paymentModeField = form.querySelector('[data-onsite-payment-mode]');
            var reasonField = form.querySelector('#close_reason');
            var narrationField = form.querySelector('#closure_narration');
            var serviceChargeField = form.querySelector('#service_charges');
            var engineerField = form.querySelector('#closure_engineer_name');
            var engineerHiddenField = form.querySelector('#closure_engineer_id');
            var productValueField = form.querySelector('#product_value');
            var customerPriceField = form.querySelector('#customer_price');
            var productProfitField = form.querySelector('[data-onsite-profit-output="product_profit"]');
            var totalProfitField = form.querySelector('[data-onsite-profit-output="total_profit"]');
            var closedByField = form.querySelector('#closed_by_brand');

            function toggleBlock(blockName, visible) {
                form.querySelectorAll('[data-close-block="' + blockName + '"]').forEach(function (element) {
                    element.hidden = !visible;
                });
            }

            function setRequired(field, required) {
                if (!field) {
                    return;
                }
                if (required) {
                    field.setAttribute('required', 'required');
                } else {
                    field.removeAttribute('required');
                    field.setCustomValidity('');
                }
            }

            function updateProfitOutputs() {
                var serviceCharges = parseMoneyValue(serviceChargeField && serviceChargeField.value);
                var productValue = parseMoneyValue(productValueField && productValueField.value);
                var customerPrice = parseMoneyValue(customerPriceField && customerPriceField.value);
                var productProfit = customerPrice - productValue;
                var totalProfit = serviceCharges + productProfit;
                if (productProfitField) {
                    productProfitField.value = productProfit.toFixed(2);
                }
                if (totalProfitField) {
                    totalProfitField.value = totalProfit.toFixed(2);
                }
            }

            function updateCloseFormState() {
                var finalStatus = finalStatusField ? finalStatusField.value : '';
                var completionType = completionTypeField ? completionTypeField.value : '';
                var paymentMode = paymentModeField ? paymentModeField.value : '';
                var isFailedOrCancelled = finalStatus === 'Failed' || finalStatus === 'Cancelled';
                var isCompleted = finalStatus === 'Completed';
                var isWarrantyOrFree = isCompleted && (completionType === 'Warranty Service' || completionType === 'Free Service');
                var isPaidService = isCompleted && completionType === 'Paid Service';

                toggleBlock('reason', isFailedOrCancelled);
                toggleBlock('completion-type', isCompleted);
                toggleBlock('narration', isWarrantyOrFree);
                toggleBlock('service-charges', isPaidService);
                toggleBlock('engineer', isPaidService);
                toggleBlock('product-value', isPaidService);
                toggleBlock('customer-price', isPaidService);
                toggleBlock('product-profit', isPaidService);
                toggleBlock('total-profit', isPaidService);
                toggleBlock('closed-by', isPaidService);
                toggleBlock('payment-mode', isPaidService);
                toggleBlock('payment-hint', isPaidService && paymentMode === 'Credit');

                setRequired(reasonField, isFailedOrCancelled);
                setRequired(completionTypeField, isCompleted);
                setRequired(narrationField, isWarrantyOrFree);
                setRequired(serviceChargeField, isPaidService);
                setRequired(productValueField, isPaidService);
                setRequired(customerPriceField, isPaidService);
                setRequired(closedByField, isPaidService);
                setRequired(paymentModeField, isPaidService);
                if (engineerField) {
                    engineerField.setAttribute('data-engineer-required', isPaidService ? '1' : '0');
                    if (!isPaidService) {
                        clearEngineerSelection(engineerField, true);
                    }
                }
                if (!isFailedOrCancelled && reasonField) {
                    reasonField.value = '';
                }
                if (!isWarrantyOrFree && narrationField) {
                    narrationField.value = '';
                }
                if (!isPaidService) {
                    if (engineerHiddenField) {
                        engineerHiddenField.value = '';
                        engineerHiddenField.removeAttribute('data-selected-label');
                    }
                    if (paymentModeField) {
                        paymentModeField.selectedIndex = 0;
                    }
                    if (closedByField) {
                        closedByField.selectedIndex = 0;
                    }
                    if (serviceChargeField) {
                        serviceChargeField.value = '0.00';
                    }
                    if (productValueField) {
                        productValueField.value = '0.00';
                    }
                    if (customerPriceField) {
                        customerPriceField.value = '0.00';
                    }
                }
                updateProfitOutputs();
            }

            [finalStatusField, completionTypeField, paymentModeField, serviceChargeField, productValueField, customerPriceField].forEach(function (field) {
                if (!field) {
                    return;
                }
                field.addEventListener('change', updateCloseFormState);
                field.addEventListener('input', updateProfitOutputs);
            });

            updateCloseFormState();
        });
    }

    function bindProfitReportToggles() {
        document.querySelectorAll('[data-onsite-profit-toggle]').forEach(function (button) {
            if (button.__onsiteProfitToggleBound) {
                return;
            }
            button.__onsiteProfitToggleBound = true;
            button.addEventListener('click', function () {
                var targetId = button.getAttribute('data-onsite-profit-toggle');
                var panel = targetId ? document.getElementById(targetId) : null;
                if (!panel) {
                    return;
                }
                var isExpanded = button.getAttribute('aria-expanded') === 'true';
                button.setAttribute('aria-expanded', isExpanded ? 'false' : 'true');
                panel.hidden = isExpanded;
                if (!isExpanded) {
                    panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                }
            });
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () {
            bindEngineerLoaders();
            bindEngineerSearchInputs();
            bindFilterFormReset();
            bindFilterPanelToggles();
            bindCreateForms();
            bindCloseForms();
            bindProfitReportToggles();
        });
    } else {
        bindEngineerLoaders();
        bindEngineerSearchInputs();
        bindFilterFormReset();
        bindFilterPanelToggles();
        bindCreateForms();
        bindCloseForms();
        bindProfitReportToggles();
    }
})();
