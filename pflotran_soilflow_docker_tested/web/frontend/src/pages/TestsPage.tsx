import { useState } from "react";
import { getJob, runTest, runTestSuite, runVisualization } from "../api/client";
import { ErrorNotice } from "../components/ErrorNotice";
import { JobStatusBadge } from "../components/JobStatusBadge";
import { ROUTES } from "../routes";
import { analyticalTestGroups } from "../testDefinitions";
import type { JobCreated, JobRead, JobStatus } from "../types";

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
      const job = testName === "all" ? await runTestSuite() : await runTest(testName);
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
