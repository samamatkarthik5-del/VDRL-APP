document.addEventListener("DOMContentLoaded", function () {
    const teamField = document.getElementById(
        "id_project_team"
    );

    const managerField = document.getElementById(
        "id_project_manager"
    );

    const aeField = document.getElementById(
        "id_application_engineer"
    );

    const dcField = document.getElementById(
        "id_document_controller"
    );

    const backupField = document.getElementById(
        "id_backup_document_controllers"
    );

    if (!teamField) {
        return;
    }

    const urlTemplate =
        teamField.dataset.membersUrlTemplate;

    if (!urlTemplate) {
        return;
    }

    function selectedValues(field) {
        if (!field) {
            return [];
        }

        return Array.from(
            field.selectedOptions
        ).map(function (option) {
            return String(option.value);
        });
    }

    function replaceOptions(
        field,
        records,
        selected,
        includeBlank
    ) {
        if (!field) {
            return;
        }

        field.innerHTML = "";

        if (includeBlank) {
            const blankOption =
                document.createElement("option");

            blankOption.value = "";
            blankOption.textContent = "---------";

            field.appendChild(blankOption);
        }

        records.forEach(function (record) {
            const option =
                document.createElement("option");

            option.value = String(record.id);
            option.textContent = record.name;

            if (
                selected.includes(
                    String(record.id)
                )
            ) {
                option.selected = true;
            }

            field.appendChild(option);
        });
    }

    async function loadTeamMembers() {
        const teamId = teamField.value;

        const selectedAe = selectedValues(
            aeField
        );

        const selectedDc = selectedValues(
            dcField
        );

        const selectedBackup = selectedValues(
            backupField
        );

        if (!teamId) {
            replaceOptions(
                managerField,
                [],
                [],
                true
            );

            replaceOptions(
                aeField,
                [],
                [],
                true
            );

            replaceOptions(
                dcField,
                [],
                [],
                true
            );

            replaceOptions(
                backupField,
                [],
                [],
                false
            );

            return;
        }

        const url = urlTemplate.replace(
            "__team_id__",
            teamId
        );

        try {
            const response = await fetch(
                url,
                {
                    headers: {
                        "X-Requested-With":
                            "XMLHttpRequest",
                    },
                }
            );

            if (!response.ok) {
                throw new Error(
                    "Unable to load team members."
                );
            }

            const data = await response.json();

            replaceOptions(
                managerField,
                [
                    data.project_manager,
                ],
                [
                    String(
                        data.project_manager.id
                    ),
                ],
                false
            );

            replaceOptions(
                aeField,
                data.application_engineers,
                selectedAe,
                true
            );

            replaceOptions(
                dcField,
                data.document_controllers,
                selectedDc,
                true
            );

            replaceOptions(
                backupField,
                data.document_controllers,
                selectedBackup,
                false
            );

        } catch (error) {
            console.error(error);
        }
    }

    teamField.addEventListener(
        "change",
        loadTeamMembers
    );

    if (teamField.value) {
        loadTeamMembers();
    }
});