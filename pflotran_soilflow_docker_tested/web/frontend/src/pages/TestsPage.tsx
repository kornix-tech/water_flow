import { useState } from "react";
import { createSoilCurve, getInputWorkbook, getJob, runCalculation, runTest, runTestSuite, runVisualization, saveInputWorkbook } from "../api/client";
import { ErrorNotice } from "../components/ErrorNotice";
import { JobStatusBadge } from "../components/JobStatusBadge";
import { ROUTES } from "../routes";
import { analyticalTestGroups } from "../testDefinitions";
import type { InputTab, InputWorkbook, JobCreated, JobRead, JobStatus, SoilCurveTableCreate } from "../types";

interface TestExecutionWorkflow {
  testJobId: string;
  testStatus: JobStatus;
  runName: string | null;
  visualizationJobId: string | null;
  visualizationStatus: JobStatus | null;
  viewReady: boolean;
}

const terminalJobStatuses: JobStatus[] = ["success", "failed", "cancelled"];

function isTerminal(status: JobStatus): boolean {
  return terminalJobStatuses.includes(status);
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function updateWorkbookField(tab: InputTab, key: string, value: string | number | boolean | null): InputTab {
  return {
    ...tab,
    fields: tab.fields.map((field) => (field.key === key ? { ...field, value } : field))
  };
}

function updateWorkbookFields(workbook: InputWorkbook, updates: Record<string, string | number | boolean | null>): InputWorkbook {
  return {
    ...workbook,
    calculation_id: null,
    calculation_title: null,
    calculation_created_at: null,
    calculation_status: null,
    tabs: workbook.tabs.map((tab) => {
      if (tab.kind !== "fields") {
        return tab;
      }
      return Object.entries(updates).reduce((nextTab, [key, value]) => updateWorkbookField(nextTab, key, value), tab);
    })
  };
}

function tabularDemoCurves(): SoilCurveTableCreate[] {
  return [
    {
      curve_name: "tabular_demo_retention",
      curve_kind: "retention",
      retention_model: "tabular",
      conductivity_model: null,
      pressure_unit: "Па",
      saturation_unit: "безразмерная насыщенность",
      conductivity_unit: "безразмерная",
      comment: "Демо-кривая Pc(S) для проверки полного табличного расчетного workflow.",
      points: [
        { point_index: 0, pressure_head_m: null, pressure_pa: 100000, water_content: null, saturation: 0.2, relative_permeability: null, hydraulic_conductivity_m_s: null, comment: "остаточная область" },
        { point_index: 1, pressure_head_m: null, pressure_pa: 20000, water_content: null, saturation: 0.6, relative_permeability: null, hydraulic_conductivity_m_s: null, comment: "переходная область" },
        { point_index: 2, pressure_head_m: null, pressure_pa: 0, water_content: null, saturation: 1.0, relative_permeability: null, hydraulic_conductivity_m_s: null, comment: "насыщение" }
      ]
    },
    {
      curve_name: "tabular_demo_conductivity",
      curve_kind: "conductivity",
      retention_model: "tabular",
      conductivity_model: "tabular",
      pressure_unit: "Па",
      saturation_unit: "безразмерная насыщенность",
      conductivity_unit: "безразмерная",
      comment: "Демо-кривая kr(S) для проверки PCHIP_LIQ.",
      points: [
        { point_index: 0, pressure_head_m: null, pressure_pa: null, water_content: null, saturation: 0.2, relative_permeability: 0.0, hydraulic_conductivity_m_s: null, comment: "остаточная область" },
        { point_index: 1, pressure_head_m: null, pressure_pa: null, water_content: null, saturation: 0.6, relative_permeability: 0.25, hydraulic_conductivity_m_s: null, comment: "переходная область" },
        { point_index: 2, pressure_head_m: null, pressure_pa: null, water_content: null, saturation: 1.0, relative_permeability: 1.0, hydraulic_conductivity_m_s: null, comment: "насыщение" }
      ]
    }
  ];
}

export function TestsPage({ onNavigate }: { onNavigate: (path: string) => void }) {
  const [latestCreatedJob, setLatestCreatedJob] = useState<JobCreated | null>(null);
  const [workflowByTestName, setWorkflowByTestName] = useState<Record<string, TestExecutionWorkflow>>({});
  const [workflowErrorMessage, setWorkflowErrorMessage] = useState("");

  function updateTestExecutionWorkflow(testName: string, patch: Partial<TestExecutionWorkflow>) {
    setWorkflowByTestName((current) => {
      const previousWorkflow = current[testName];
      if (!previousWorkflow) {
        return current;
      }
      return { ...current, [testName]: { ...previousWorkflow, ...patch } };
    });
  }

  async function waitForJobToFinish(jobId: string, onUpdate: (job: JobRead) => void): Promise<JobRead> {
    for (;;) {
      const job = await getJob(jobId);
      onUpdate(job);
      if (isTerminal(job.status)) {
        return job;
      }
      await sleep(2000);
    }
  }

  async function monitorTestAndVisualization(testName: string, initialJob: JobCreated) {
    const finishedTest = await waitForJobToFinish(initialJob.job_id, (job) => {
      updateTestExecutionWorkflow(testName, {
        testStatus: job.status,
        runName: job.run_name
      });
    });
    if (finishedTest.status !== "success") {
      setWorkflowErrorMessage(finishedTest.error_message ?? "Расчетное задание завершилось ошибкой");
      return;
    }
    if (!finishedTest.run_name) {
      updateTestExecutionWorkflow(testName, { viewReady: false });
      return;
    }

    const visualizationJob = await runVisualization(finishedTest.run_name);
    updateTestExecutionWorkflow(testName, {
      visualizationJobId: visualizationJob.job_id,
      visualizationStatus: visualizationJob.status
    });
    const finishedVisualization = await waitForJobToFinish(visualizationJob.job_id, (job) => {
      updateTestExecutionWorkflow(testName, {
        visualizationStatus: job.status
      });
    });
    updateTestExecutionWorkflow(testName, {
      viewReady: finishedVisualization.status === "success"
    });
  }

  async function startTestWorkflow(testName: string) {
    setWorkflowErrorMessage("");
    try {
      const job = testName === "tabular_full_demo" ? await startTabularDemoCalculation() : testName === "all" ? await runTestSuite() : await runTest(testName);
      setLatestCreatedJob(job);
      setWorkflowByTestName((current) => ({
        ...current,
        [testName]: {
          testJobId: job.job_id,
          testStatus: job.status,
          runName: job.run_name,
          visualizationJobId: null,
          visualizationStatus: null,
          viewReady: false
        }
      }));
      monitorTestAndVisualization(testName, job).catch((caught) => {
        setWorkflowErrorMessage(caught instanceof Error ? caught.message : "Не удалось выполнить тестовый workflow");
      });
    } catch (caught) {
      setWorkflowErrorMessage(caught instanceof Error ? caught.message : "Не удалось поставить тест в очередь");
    }
  }

  async function startTabularDemoCalculation(): Promise<JobCreated> {
    const workbook = await getInputWorkbook();
    const demoWorkbook = updateWorkbookFields(workbook, {
      project_name: "tabular_full_demo",
      retention_model: "tabular",
      conductivity_model: "tabular",
      final_time_days: 0.01,
      maximum_timestep_days: 0.005,
      output_interval_days: 0.005
    });
    const savedWorkbook = await saveInputWorkbook(demoWorkbook);
    if (!savedWorkbook.calculation_id) {
      throw new Error("Не удалось создать расчет для табличного демо-сценария");
    }
    for (const curve of tabularDemoCurves()) {
      await createSoilCurve(savedWorkbook.calculation_id, curve);
    }
    return runCalculation(savedWorkbook.calculation_id);
  }

  return (
    <section>
      <div className="page-title">
        <h1>Тесты</h1>
        <button type="button" onClick={() => onNavigate(ROUTES.jobs)}>
          Открыть статус
        </button>
      </div>
      <ErrorNotice message={workflowErrorMessage} />
      <div className="panel">
        <div className="test-list">
          {analyticalTestGroups.map((group) => (
            <details className="test-group" key={group.title}>
              <summary className="test-group-summary">
                <span>{group.title}</span>
              </summary>
              <div className="test-group-body">
                <p className="test-group-description">{group.description}</p>
                {group.tests.map((test) => {
                  const workflow = workflowByTestName[test.name];
                  return (
                    <article className="test-row" key={test.name}>
                      <div className="test-actions">
                        <button className="primary" type="button" onClick={() => startTestWorkflow(test.name)}>
                          {test.label}
                        </button>
                        {workflow && (
                          <div className="test-workflow-status">
                            <span>Тест: </span>
                            <JobStatusBadge status={workflow.testStatus} />
                            {workflow.visualizationStatus && (
                              <>
                                <span>Графики: </span>
                                <JobStatusBadge status={workflow.visualizationStatus} />
                              </>
                            )}
                          </div>
                        )}
                        {workflow?.viewReady && workflow.runName && (
                          <button type="button" onClick={() => onNavigate(`${ROUTES.visualization}?run=${workflow.runName}`)}>
                            Открыть графики
                          </button>
                        )}
                      </div>
                      <div className="test-description">
                        <h3>{test.title}</h3>
                        <p>{test.description}</p>
                        <p>
                          <strong>Аналитическое сравнение:</strong> {test.analytical}
                        </p>
                      </div>
                    </article>
                  );
                })}
              </div>
            </details>
          ))}
        </div>
        {latestCreatedJob && (
          <div className="notice">
            задание: <span className="mono">{latestCreatedJob.job_id}</span>
          </div>
        )}
      </div>
    </section>
  );
}
