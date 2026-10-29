/* Dashboard: list, search, filter, add, edit and delete students. */
(function () {
  const rows = document.getElementById("studentRows");
  const emptyState = document.getElementById("emptyState");
  const emptyText = document.getElementById("emptyText");
  const loadError = document.getElementById("loadError");
  const searchBox = document.getElementById("searchBox");
  const riskFilter = document.getElementById("riskFilter");

  const studentModal = new bootstrap.Modal(document.getElementById("studentModal"));
  const deleteModal = new bootstrap.Modal(document.getElementById("deleteModal"));
  const form = document.getElementById("studentForm");
  const formError = document.getElementById("studentFormError");
  const saveBtn = document.getElementById("studentSaveBtn");

  let students = [];
  let pendingDeleteId = null;

  async function load() {
    const params = new URLSearchParams();
    if (searchBox.value.trim()) params.set("q", searchBox.value.trim());
    if (riskFilter.value) params.set("risk", riskFilter.value);
    try {
      const data = await api("/api/students?" + params.toString());
      loadError.classList.add("d-none");
      students = data.students;
      renderSummary(data.summary);
      renderRows();
      const filtering = searchBox.value.trim() || riskFilter.value;
      emptyText.textContent = filtering
        ? "No students match your search."
        : "No students yet. Add your first student to begin.";
    } catch (e) {
      loadError.textContent = e.message;
      loadError.classList.remove("d-none");
    }
  }

  function renderSummary(s) {
    document.getElementById("sTotal").textContent = s.total;
    document.getElementById("sHigh").textContent = s.High;
    document.getElementById("sMod").textContent = s.Moderate;
    document.getElementById("sLow").textContent = s.Low;
  }

  function renderRows() {
    emptyState.classList.toggle("d-none", students.length > 0);
    rows.innerHTML = students.map(s => {
      const avg = s.risk.average === null ? "–" : s.risk.average.toFixed(1);
      const att = s.risk.attendance_rate === null ? "–" : Math.round(s.risk.attendance_rate) + "%";
      return `<tr>
        <td><a class="student-link" href="/students/${s.id}">${esc(s.last_name)}, ${esc(s.first_name)}</a>
            <div class="small text-secondary">${esc(s.student_no)} · Year ${s.year_level}</div></td>
        <td>${esc(s.course)}</td>
        <td class="text-center">${avg}</td>
        <td class="text-center">${att}</td>
        <td>${riskBadge(s.risk.level)}</td>
        <td class="text-end text-nowrap">
          <a class="btn btn-sm btn-outline-primary" href="/students/${s.id}" aria-label="Open ${esc(s.first_name)} ${esc(s.last_name)}"><i class="bi bi-eye"></i></a>
          <button class="btn btn-sm btn-outline-secondary" data-edit="${s.id}" aria-label="Edit ${esc(s.first_name)} ${esc(s.last_name)}"><i class="bi bi-pencil"></i></button>
          <button class="btn btn-sm btn-outline-danger" data-delete="${s.id}" aria-label="Delete ${esc(s.first_name)} ${esc(s.last_name)}"><i class="bi bi-trash"></i></button>
        </td></tr>`;
    }).join("");
  }

  function openForm(student) {
    form.reset();
    clearFieldErrors(form);
    formError.classList.add("d-none");
    document.getElementById("studentId").value = student ? student.id : "";
    document.getElementById("studentModalTitle").textContent = student ? "Edit student" : "Add student";
    if (student) {
      ["student_no", "first_name", "last_name", "course", "year_level", "email"].forEach(k => {
        document.getElementById("f_" + k).value = student[k] ?? "";
      });
    }
    studentModal.show();
  }

  form.addEventListener("submit", async e => {
    e.preventDefault();
    clearFieldErrors(form);
    formError.classList.add("d-none");
    const id = document.getElementById("studentId").value;
    const body = {};
    ["student_no", "first_name", "last_name", "course", "year_level", "email"].forEach(k => {
      body[k] = document.getElementById("f_" + k).value;
    });
    saveBtn.disabled = true;
    try {
      await api(id ? `/api/students/${id}` : "/api/students", { method: id ? "PUT" : "POST", body });
      studentModal.hide();
      toast(id ? "Student updated." : "Student added.");
      load();
    } catch (err) {
      showFieldErrors(form, err.fields, "f_");
      formError.textContent = err.message;
      formError.classList.remove("d-none");
    } finally {
      saveBtn.disabled = false;
    }
  });

  rows.addEventListener("click", e => {
    const edit = e.target.closest("[data-edit]");
    const del = e.target.closest("[data-delete]");
    if (edit) openForm(students.find(s => s.id === Number(edit.dataset.edit)));
    if (del) {
      const s = students.find(x => x.id === Number(del.dataset.delete));
      pendingDeleteId = s.id;
      document.getElementById("deleteText").textContent = `Delete ${s.first_name} ${s.last_name}?`;
      deleteModal.show();
    }
  });

  document.getElementById("confirmDeleteBtn").addEventListener("click", async () => {
    try {
      await api(`/api/students/${pendingDeleteId}`, { method: "DELETE" });
      deleteModal.hide();
      toast("Student deleted.");
      load();
    } catch (err) {
      deleteModal.hide();
      toast(err.message, "error");
    }
  });

  document.getElementById("addStudentBtn").addEventListener("click", () => openForm(null));
  searchBox.addEventListener("input", debounce(load, 250));
  riskFilter.addEventListener("change", load);
  load();
})();
