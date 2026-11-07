document.addEventListener("DOMContentLoaded", function () {
    if (typeof Chart === "undefined" || typeof dashboardData === "undefined") return;

    const palette = ['#2563eb', '#16a34a', '#f59e0b', '#dc2626', '#7c3aed', '#0891b2'];

    function barChart(id, block, axisMax) {
        const el = document.getElementById(id);
        if (!el || !block) return;
        new Chart(el, {
            type: 'bar',
            data: {
                labels: block.labels,
                datasets: [{
                    label: 'Average Grade',
                    data: block.values,
                    backgroundColor: palette,
                    borderWidth: 1
                }]
            },
            options: {
                responsive: true,
                plugins: { legend: { display: false } },
                scales: { y: { beginAtZero: true, max: axisMax } }
            }
        });
    }

    barChart('programChart', dashboardData.programs, 100);
    barChart('subjectChart', dashboardData.subjects, 100);
    barChart('yearChart', dashboardData.years, 100);

    const pf = document.getElementById('passFailChart');
    if (pf) {
        new Chart(pf, {
            type: 'pie',
            data: {
                labels: ['Passed', 'Failed'],
                datasets: [{ data: dashboardData.passFail, backgroundColor: ['#22c55e', '#ef4444'] }]
            },
            options: { responsive: true }
        });
    }

    const sc = document.getElementById('scatterChart');
    if (sc) {
        new Chart(sc, {
            type: 'scatter',
            data: {
                datasets: [{
                    label: 'Student',
                    data: dashboardData.scatter,
                    backgroundColor: '#2563eb'
                }]
            },
            options: {
                responsive: true,
                plugins: { legend: { display: false } },
                scales: {
                    x: { title: { display: true, text: 'Attendance Rate (%)' } },
                    y: { title: { display: true, text: 'Grade' } }
                }
            }
        });
    }
});
