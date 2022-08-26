import argparse
import pyBigWig
import pyfaidx
import subprocess
import tempfile
import os
import numpy as np
import auto_shift_detect


def parse_args():
    parser=argparse.ArgumentParser(description="Automatically detect enzyme shift of input BAM/Fragment File")
    parser.add_argument('-g','--genome', required=True, type=str, help="reference genome file")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('-ibam', '--input-bam-file', type=str, help="Input BAM file")
    group.add_argument('-ifrag', '--input-fragment-file', type=str, help="Input fragment file")
    group.add_argument('-itag', '--input-tagalign-file', type=str, help="Input tagAlign file")
    parser.add_argument('-c', '--chrom-sizes', type=str, required=True, help="Chrom sizes file")
    parser.add_argument('-o', '--output-prefix', type=str, required=True, help="Output prefix (path/to/prefix)")
    parser.add_argument('-d', '--data-type', required=True, type=str, choices=['ATAC', 'DNASE'], help="assay type")
    parser.add_argument('-p', '--plus-shift', type=int, default=None, help="Plus strand shift applied to reads. Estimated if not specified")
    parser.add_argument('-m', '--minus-shift', type=int, default=None, help="Minus strand shift applied to reads. Estimated if not specified")
    parser.add_argument('--ATAC-ref-path', type=str, default=None, help="Path to ATAC reference motifs (ATAC.ref.motifs.txt used by default)")
    parser.add_argument('--DNASE-ref-path', type=str, default=None, help="Path to DNASE reference motifs (DNASE.ref.motifs.txt used by default)")
    parser.add_argument('--num-samples', type=int, default=10000, help="Number of reads to sample from BAM/fragment/tagAlign file for shift estimation")
    args = parser.parse_args()
    return args


def generate_bigwig(input_bam_file, input_fragment_file, input_tagalign_file, output_prefix, genome_fasta_file, chrom_sizes_file, plus_shift_delta, minus_shift_delta):
    assert (input_bam_file is None) + (input_fragment_file is None) + (input_tagalign_file is None) == 2, "Only one input file!"

    if input_bam_file:
        p1 = auto_shift_detect.bam_to_tagalign_stream(input_bam_file)
    elif input_fragment_file:
        p1 = auto_shift_detect.fragment_to_tagalign_stream(input_fragment_file)
    elif input_tagalign_file:
        p1 = auto_shift_detect.tagalign_stream(input_tagalign_file)

    cmd = """awk -v OFS="\\t" '{{if ($6=="+"){{print $1,$2{0:+},$3{0:+},$4,$5,$6}} else if ($6=="-") {{print $1,$2{1:+},$3{1:+},$4,$5,$6}}}}' | sort -k1,1 | bedtools genomecov -bg -5 -i stdin -g {2} | sort -k1,1 -k2,2n""".format(plus_shift_delta, minus_shift_delta, chrom_sizes_file)

    tmp_bedgraph = tempfile.NamedTemporaryFile()
    print("Making BedGraph")
    with open(tmp_bedgraph.name, 'w') as f:
        p2 = subprocess.Popen([cmd], stdin=p1.stdout, stdout=f, shell=True)
        p1.stdout.close()
        p2.communicate()

    print("Making Bigwig")
    subprocess.run(["bedGraphToBigWig", tmp_bedgraph.name, chrom_sizes_file, output_prefix + "_unstranded.bw"])

    tmp_bedgraph.close()

def main():
    args = parse_args()

    plus_shift, minus_shift = args.plus_shift, args.minus_shift

    if (plus_shift is None) or (minus_shift is None):
        # TODO: validate inputs, check bedtools and ucsc tools
        if args.data_type=="ATAC":
            ref_motifs_file = args.ATAC_ref_path
            if ref_motifs_file is None:
                # https://stackoverflow.com/questions/4060221/how-to-reliably-open-a-file-in-the-same-directory-as-the-currently-running-scrip
                ref_motifs_file =  os.path.realpath(os.path.join(os.path.dirname(__file__), "ATAC.ref.motifs.txt"))
        elif args.data_type=="DNASE":
            ref_motifs_file = args.DNASE_ref_path
            if ref_motifs_file is None:
                ref_motifs_file =  os.path.realpath(os.path.join(os.path.dirname(__file__), "DNASE.ref.motifs.txt"))
    
        print("Estimating enzyme shift in input file")
        plus_shift, minus_shift = auto_shift_detect.compute_shift(args.input_bam_file,
                args.input_fragment_file,
                args.input_tagalign_file,
                args.num_samples,
                args.genome,
                args.data_type,
                ref_motifs_file)
    
        print("The estimated shift is: {:+}/{:+}".format(plus_shift, minus_shift))

    else:
        print("The specified shift is: {:+}/{:+}".format(plus_shift, minus_shift))

    # computing additional shifting to apply
    if args.data_type=="ATAC":
        plus_shift_delta, minus_shift_delta = 4-plus_shift, -4-minus_shift
    elif args.data_type=="DNASE":
        plus_shift_delta, minus_shift_delta = -plus_shift, 1-minus_shift

    generate_bigwig(args.input_bam_file,
            args.input_fragment_file,
            args.input_tagalign_file,
            args.output_prefix,
            args.genome,
            args.chrom_sizes,
            plus_shift_delta,
            minus_shift_delta)

if __name__=="__main__":
    main()
