import json
import os
import stat
import subprocess

from abfe.orchestration import slurm_status


class scheduler():

    def __init__(self, out_dir_path: str, n_cores: int = 1, cluster_config: dict = None) -> None:
        self.n_cores = n_cores
        self.out_dir_path = out_dir_path
        self.out_job_path = out_dir_path + "/job.sh"
        self.out_scheduler_path = out_dir_path + "/scheduler.sh"
        self.cluster_config = {'partition':'cpu','time':'96:00:00', "mem": "5000"}
        if cluster_config:
            self.cluster_config.update(cluster_config)

    def generate_scheduler_file(self, out_prefix):
        if (isinstance(self.out_job_path, str)):
            self.out_job_path = [self.out_job_path]

        file_str = [
            "#!/bin/env bash",
            "",
            # "conda activate abfe",
        ]
        # TODO: It is more general to construct dynamically any slurm command based on the cluster config, --{key} {self.cluster_config[key}}
        for i, job_path in enumerate(self.out_job_path):
            basename = os.path.basename(job_path).replace(".sh", "")
            file_str.extend([
                "",
                "cd " + os.path.dirname(job_path),
                 # TODO: str(self.n_cores) gives a to higher number, and the cluster does not have this resources.
                "job" + str(i) + f"=$(sbatch -p {self.cluster_config['partition']} --time {self.cluster_config['time']} -c " + str(self.n_cores) + " -J " + str(
                    out_prefix + "_" + basename) + "_scheduler " + job_path + ")",
                "jobID" + str(i) + "=$(echo $job" + str(i) + " | awk '{print $4}')",
                "echo \"${jobID" + str(i) + "}\"",
            ])

        if (len(self.out_job_path) > 1):
            file_str.append("\n")
            file_str.append("echo " + ":".join(["${jobID" + str(i) + "}" for i in range(len(self.out_job_path))]))
            file_str.append(f"sbatch -p {self.cluster_config['partition']} --time {self.cluster_config['time']}  --dependency=afterok:" + ":".join(
                ["${jobID" + str(i) + "}" for i in range(len(self.out_job_path))]) + " -c " + str(
                self.n_cores) + " -J " + str(out_prefix + "_final_ana") + "_scheduler " + self._final_job_path)

        file_str = "\n".join(file_str)
        file_io = open(self.out_scheduler_path, "w")
        file_io.write(file_str)
        file_io.close()
        os.chmod(self.out_scheduler_path, stat.S_IRWXU + stat.S_IRGRP + stat.S_IXGRP + stat.S_IROTH + stat.S_IXOTH)

        return self.out_scheduler_path

    def generate_job_file(self, out_prefix, cluster_conf_path: str = None, cluster=False,
                          num_jobs: int = 1, latency_wait: int = 120, snake_job=""):
        if (cluster and cluster_conf_path is not None):
            root_dir = os.path.dirname(cluster_conf_path)
            slurm_logs = os.path.dirname(cluster_conf_path) + "/slurm_logs"
            if (not os.path.exists(slurm_logs)): os.mkdir(slurm_logs)


            if (out_prefix == ""):
                name = str(out_prefix) + "{name}.{jobid}"
                log = slurm_logs + "/" + str(out_prefix) + "{name}_{jobid}"
            else:
                name = str(out_prefix) + ".{name}.{jobid}"
                log = slurm_logs + "/" + str(out_prefix) + "_{name}_{jobid}"

            self.cluster_config.update({
                "cpus-per-task": '{threads}',
                "cores-per-socket": '{threads}',
                "chdir": root_dir,
                "job-name": "\\\"" + name + "\\\"",
                "output": "\\\"" + log + ".out\\\"",
                "error": "\\\"" + log + ".err\\\""
            })

            json.dump(self.cluster_config, open(cluster_conf_path, "w"), indent="  ")
            cluster_options = " ".join(["--" + key + "=" + str(val) + " " for key, val in self.cluster_config.items()]) + " --parsable"
            status_script_path = slurm_status.__file__

            # TODO: change this here, such each job can access resource from cluster-config!
            file_str = "\n".join([
                "#!/bin/env bash",
                "snakemake --cluster \"sbatch " + cluster_options + "\" "
                            "--cluster-config " + cluster_conf_path + " "
                             "--cluster-status " + status_script_path + " "
                             "--cluster-cancel \"scancel\" "
                             "--jobs " + str(num_jobs) + " --latency-wait " + str(latency_wait) + " --rerun-incomplete " + snake_job
            ])
        elif (cluster):
            raise ValueError("give cluster conf! ")
        else:
            file_str = "\n".join([
                "#!/bin/env bash",
                "snakemake -c " + str(self.n_cores) + " -j "+str(num_jobs)+" --latency-wait " + str(
                    latency_wait) + " --rerun-incomplete " + snake_job
            ])

        file_io = open(self.out_job_path, "w")
        file_io.write(file_str)
        file_io.close()
        os.chmod(self.out_job_path, stat.S_IRWXU + stat.S_IRGRP + stat.S_IXGRP + stat.S_IROTH + stat.S_IXOTH)

        return self.out_job_path

    def schedule_run(self) -> int:
        orig_path = os.getcwd()
        os.chdir(self.out_dir_path)
        out = subprocess.getoutput(self.out_scheduler_path)

        job_id = int(out.strip())
        os.chdir(orig_path)

        return job_id

    def submit_run(self, out_prefix="ABFE", cluster=True) -> int:
        self.generate_job_file(out_prefix, cluster=cluster)
        self.generate_scheduler_file(out_prefix)
        out = self.schedule_run()
        return out
