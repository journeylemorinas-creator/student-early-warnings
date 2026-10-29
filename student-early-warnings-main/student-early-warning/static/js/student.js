/* Student detail page: risk explanation, grades (add/edit/delete), attendance (add/delete). */
(function () {
  const id = window.STUDENT_ID;
  const pageError = document.getElementById("pageError");

  const gradeForm = document.getElementById("gradeForm");
  const gradeId = document.getElementById("gradeId");
  const gSubject = document.getElementById("g_subject");
  const gTerm = document.getElementById("g_term");
  const gScore = document.getElementById("g_score");
  const gradeSaveBtn = document.getElementById("gradeSaveBtn");
  const gradeCancelBtn = document.getElementById("gradeCancelBtn");
  const attForm = document.getElementById("attForm");
  const aDate = document.getElementById("a_date");

  let grades = [];

  // Do not let the date picker go past today (the server checks this too).
  aDate.max = new Date().toISOString().slice(0, 10);
  aDate.value = aDate.max;

  async function load() {
    try {
      const data = await api(`/api/students/${id}`);
      pageError.classList.add("d-none");
      grades = data.grades;
      renderHeader(data.student, data.risk);
      renderRisk(data.risk);
      renderGrades(data.grades);
      renderAttendance(data.attendance);
    } catch (e) {
      pageError.textContent = e.message;
      pageError.classList.remove("d-none");
    }
  }

  function renderHeader(s, risk) {
    document.title = `${s.first_name} ${s.last_name} · EduWatch`;
    document.getElementById("stName").textContent = `${s.first_name} ${s.last_name}`;
    document.getElementById("stMeta").textContent =
      `${s.student_no} · ${s.course} · Year ${s.year_level}` + (s.email ? ` · ${s.email}` : "");
    document.getElementById("stBadge").innerHTML = riskBadge(risk.level);
  }

  function renderRisk(r) {
    document.getElementById("riskScore").textContent = r.score === null ? "–" : r.score;
    const bar = document.getElementById("riskBar");
    bar.style.width = (r.score || 0) + "%";
    bar.className = "progress-bar bar-" + r.level.replace(/\s+/g, "-");
    document.getElementById("avgGrade").textContent = r.average === null ? "–" : r.average.toFixed(1);
    document.getElementById("attRate").textContent = r.attendance_rate === null ? "–" : Math.round(r.attendance_rate) + "%";
    document.getElementById("riskReasons").innerHTML = r.reasons.map(x => `<li>${esc(x)}</li>`).join("");
    document.getElementById("riskSuggestions").innerHTML = r.suggestions.map(x => `<li>${esc(x)}</li>`).join("");
  }

  function renderGrades(list) {
    document.getElementById("gradeEmpty").classList.toggle("d-none", list.length > 0);
    document.getElementById("gradeRows").innerHTML = list.map(g => `<tr>
      <td>${esc(g.subject)}</td><td>${esc(g.term)}</td>
      <td class="text-end ${g.score < 75 ? "text-danger fw-semibold" : ""}">${g.score}</td>
      <td class="text-end text-nowrap">
        <button class="btn btn-sm btn-outline-secondary" data-edit-grade="${g.id}" aria-label="Edit grade"><i class="bi bi-pencil"></i></button>
        <button class="btn btn-sm btn-outline-danger" data-del-grade="${g.id}" aria-label="Delete grade"><i class="bi bi-trash"></i></button>
      </td></tr>`).join("");
  }

  function renderAttendance(list) {
    document.getElementById("attEmpty").classList.toggle("d-none", list.length > 0);
    document.getElementById("attRows").innerHTML = list.map(a => `<tr>
      <td>${esc(a.date)}</td><td>${esc(a.status)}</td>
      <td class="text-end"><button class="btn btn-sm btn-outline-danger" data-del-att="${a.id}" aria-label="Delete record"><i class="bi bi-trash"></i></button></td>
      </tr>`).join("");
  }

  function resetGradeForm() {
    gradeForm.reset();
    gradeId.value = "";
    gradeSaveBtn.textContent = "Add";
    gradeCancelBtn.classList.add("d-none");
    clearFieldErrors(gradeForm);
  }

  gradeForm.addEventListener("submit", async e => {
    e.preventDefault();
    clearFieldErrors(gradeForm);
    const body = { subject: gSubject.value, term: gTerm.value, score: gScore.value };
    try {
      if (gradeId.value) await api(`/api/grades/${gradeId.value}`, { method: "PUT", body });
      else await api(`/api/students/${id}/grades`, { method: "POST", body });
      toast(gradeId.value ? "Grade updated." : "Grade added.");
      resetGradeForm();
      load();
    } catch (err) {
      showFieldErrors(gradeForm, err.fields, "g_");
      toast(err.message, "error");
    }
  });

  gradeCancelBtn.addEventListener("click", resetGradeForm);

  document.getElementById("gradeRows").addEventListener("click", async e => {
    const edit = e.target.closest("[data-edit-grade]");
    const del = e.target.closest("[data-del-grade]");
    if (edit) {
      const g = grades.find(x => x.id === Number(edit.dataset.editGrade));
      gradeId.value = g.id; gSubject.value = g.subject; gTerm.value = g.term; gScore.value = g.score;
      gradeSaveBtn.textContent = "Save";
      gradeCancelBtn.classList.remove("d-none");
      gSubject.focus();
    }
    if (del && confirm("Delete this grade?")) {
      try { await api(`/api/grades/${del.dataset.delGrade}`, { method: "DELETE" }); toast("Grade deleted."); load(); }
      catch (err) { toast(err.message, "error"); }
    }
  });

  attForm.addEventListener("submit", async e => {
    e.preventDefault();
    clearFieldErrors(attForm);
    try {
      await api(`/api/students/${id}/attendance`, {
        method: "POST", body: { date: aDate.value, status: document.getElementById("a_status").value } });
      toast("Attendance recorded.");
      load();
    } catch (err) {
      showFieldErrors(attForm, err.fields, "a_");
      toast(err.message, "error");
    }
  });

  document.getElementById("attRows").addEventListener("click", async e => {
    const del = e.target.closest("[data-del-att]");
    if (del && confirm("Delete this attendance record?")) {
      try { await api(`/api/attendance/${del.dataset.delAtt}`, { method: "DELETE" }); toast("Record deleted."); load(); }
      catch (err) { toast(err.message, "error"); }
    }
  });

  load();
})();
