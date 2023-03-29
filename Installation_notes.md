# Package installation:

1. download the newest version of Anaconda3 from:

2. Install anaconda to ```C:\Users\neoSTORM6\anaconda3```

3. create a conda environment called "halenv" by:

    ```cmd
    conda create -n halenv
    ```

4. Install required package by: 

    ```cmd
    conda install numpy pip pillow pywin32 pyserial scipy
    conda install tifffile
    pip install PyQt5
    pip install PyDAQmx
    ```

5. clone the github repo by: 

    ```cmd
    git clone https://github.com/zhengpuas47/STORM6.git
    ```

6. add this STORM6 folder into PATH enviromental variable (I have done it manually in Windows)

7. follow the installation guide from source using Anaconda3: [link](https://storm-analysis.readthedocs.io/en/stable/install.html#using-anaconda)

    ```cmd
    conda config --add channels conda-forge
    conda install numpy pytest pytest-runner m2w64-toolchain tifffile scipy h5py astropy matplotlib pillow shapely randomcolor pywavelets scons
    cd storm-analysis
    scons -Q compiler=mingw
    python setup.py install
    ```

8. after properly installed required packages, adjust the following:
    * use UC480 camera viewer to adjust IR crop, and best tune its dynamic range.
    * use National Instruments software "NI MAX" to properly detect Daq card, write corresponding name in the xml file that hal4000.py used.

Unsolved questions:
1. find a working hal protocol
2. worked code to wakeup lumencor:
```cmd
WAKEUP
set TTLENABLE 1
```
how to integrate this into a dave?
3. does copy data / find focus works in the new Dave?